"""Build profile/results/costs.csv: model cost per call site (Homework 9 Part A).

Usage (from the repository root, with the local Langfuse running):
    uv run python profile/scripts/cost_profile.py

Rows cover three call sites:

- ``server/app.py:229``: the agent's model calls in the Homework 3 run, from
  the exported traces in ``traces/support_traces.json``.
- ``analysis/run_judges.py:179`` at commit dcca46e: the Homework 5 judge runs
  (v0 development, v1 development and test).
- ``analysis/run_judges.py:180``: the same judge request in the Homework 7
  monitor (before, after twice, and the scheduled workflow run).

No source saved token counts: the HW3 export has zero usage on every
generation and no generation output, and the judge runs kept only the
critique. Every count is therefore an estimate made with tiktoken's
cl100k_base encoding, which approximates the Claude and Llama tokenizers:

- agent input: each generation's logged system prompt and messages, plus the
  tool definitions sent with every request (taken from the current agent code);
- agent output: the visible output, i.e. each trace's final reply plus the
  name and arguments of every tool call;
- judge input: the frozen prompt plus the rendered transcript exactly as the
  judge received it;
- judge output: the saved critique, which keeps at most the last 1,200
  characters, so judge output is a lower bound. Retries were not recorded.

Prices come from optimize/config.json (dated there).
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

import tiktoken  # noqa: E402

OUTPUT = REPO_ROOT / "profile" / "results" / "costs.csv"
AGENT_MODEL = "openai/claude-5-sonnet-gosys"
JUDGE_MODEL = "openai/llama4-maverick-17b-128e-instruct"
ENCODING = tiktoken.get_encoding("cl100k_base")


def tokens(text: str) -> int:
    return len(ENCODING.encode(text, disallowed_special=()))


def strings(value: Any) -> list[str]:
    """Every string value in a logged message, skipping structural fields."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for k, v in value.items() if k not in {"type", "id", "role"} for s in strings(v)]
    if isinstance(value, list):
        return [s for item in value for s in strings(item)]
    return []


def prices() -> dict[str, tuple[float, float]]:
    config = json.loads((REPO_ROOT / "optimize" / "config.json").read_text())
    return {
        model: (float(p["input"]), float(p["output"]))
        for model, p in config["prices_per_million_tokens_usd"].items()
    }


def tool_definition_tokens() -> dict[str, int]:
    """Tokens in the tool definitions the agent sends, per role."""
    from agent.agent import TOOLS_BY_ROLE

    return {
        role: sum(
            tokens(json.dumps({"name": t.name, "description": t.description,
                               "parameters": t.params_json_schema}))
            for t in tools
        )
        for role, tools in TOOLS_BY_ROLE.items()
    }


def _attributes(obj: dict[str, Any]) -> dict[str, Any]:
    raw = (obj.get("metadata") or {}).get("attributes")
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except ValueError:
            return {}
    return raw or {}


def agent_row() -> dict[str, Any]:
    export = json.loads((REPO_ROOT / "traces" / "support_traces.json").read_text())
    tool_tokens = tool_definition_tokens()
    calls = input_tokens = output_tokens = 0
    for trace in export["traces"]:
        role = _attributes(trace).get("cartwheel.user_role", "shopper")
        observations = trace.get("observations") or []
        for obs in observations:
            if obs.get("type") == "GENERATION":
                calls += 1
                input_tokens += tokens("\n".join(strings(obs.get("input")))) + tool_tokens.get(role, 0)
            elif obs.get("type") in {"TOOL", "SPAN"} and obs.get("name") in {
                "get_order", "list_my_orders", "find_order", "search_products",
                "search_help_center", "get_policy", "issue_refund", "cancel_order",
                "escalate_to_human",
            }:
                output_tokens += tokens(obs["name"] + json.dumps(obs.get("input")))
        output_tokens += tokens("\n".join(strings(trace.get("output"))))
    return {
        "cost_category": "customer_conversation",
        "call_site": "server/app.py:229",
        "purpose": (
            f"Agent replies and tool calls in the Homework 3 run ({len(export['traces'])} traces, "
            f"{export['scenario_count']} scenarios). Estimated tokens: no usage was saved; input from "
            "logged prompts plus tool definitions, output from replies and tool-call arguments."
        ),
        "model": AGENT_MODEL,
        "calls": calls,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }


def judge_message(prompt: str, body: str) -> str:
    return f"{prompt}\n\nTRANSCRIPT\n----------\n{body}\n----------\n"


def hw5_row() -> dict[str, Any]:
    from analysis.run_judges import _render

    state = REPO_ROOT / "analysis" / "state"
    inputs = {r["trace_id"]: r for r in json.loads((state / "hw5b_trace_inputs.json").read_text())}
    calls = input_tokens = output_tokens = 0
    for judge_id, splits in (("missing_policy_citation_hw5-v0", ("dev",)),
                             ("missing_policy_citation_hw5-v1", ("dev", "test"))):
        judge = json.loads((state / "judges" / f"{judge_id}.json").read_text())
        for split in splits:
            critiques = json.loads((state / f"critiques-{judge_id}-{split}.json").read_text())
            for trace_id, critique in critiques.items():
                body = _render(inputs[trace_id]["trace"])[:14000]
                calls += 1
                input_tokens += tokens(judge_message(judge["prompt_text"], body))
                output_tokens += tokens(critique)
    return {
        "cost_category": "judge",
        "call_site": "analysis/run_judges.py:179 (commit dcca46e)",
        "purpose": (
            "Homework 5 missing_policy_citation judge: v0 development (40), v1 development and "
            "test (80). Estimated tokens: input from the frozen prompt and rendered transcripts; "
            "output from saved critiques (last 1,200 characters, so a lower bound); retries unknown."
        ),
        "model": JUDGE_MODEL,
        "calls": calls,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }


def hw7_row() -> dict[str, Any]:
    from monitoring.run import _parse_time, fetch_traces, period_conversations
    from observability.instrument import load_env

    load_env()
    config = json.loads((REPO_ROOT / "monitoring" / "config.json").read_text())
    judge = json.loads(
        (REPO_ROOT / "analysis" / "state" / "judges" / f"{config['judge_id']}.json").read_text()
    )
    scenario_ids = {
        json.loads(line)["id"]
        for line in (REPO_ROOT / config["scenarios"]).read_text().splitlines() if line.strip()
    }
    texts: dict[str, str] = {}
    for period in config["periods"]:
        traces = fetch_traces(_parse_time(period["from"]), _parse_time(period["to"]))
        conversations, _ = period_conversations(traces, scenario_ids, config["model"])
        texts.update({c["id"]: c["text"] for c in conversations})

    runs = [  # (saved output, number of times that judged set was run)
        (REPO_ROOT / "monitoring" / "output" / "before.json", 1),
        (REPO_ROOT / "monitoring" / "output" / "after.json", 2),
        (REPO_ROOT / ".harbor" / "ci-evidence" / "monitor-38511489046" / "artifact"
         / "last24h-2026-10-14T0427Z.json", 1),
    ]
    calls = input_tokens = output_tokens = 0
    for path, repeats in runs:
        for item in json.loads(path.read_text())["judged"]:
            body = texts[item["trace_id"]][:14000]
            calls += repeats
            input_tokens += repeats * tokens(judge_message(judge["prompt_text"], body))
            output_tokens += repeats * tokens(item["critique"])
    return {
        "cost_category": "judge",
        "call_site": "analysis/run_judges.py:180 (via monitoring/run_judges.py)",
        "purpose": (
            "Homework 7 monitor with the frozen missing_policy_citation judge: before (36), after "
            "twice (72), scheduled workflow run (32). Estimated tokens as for Homework 5; transcripts "
            "re-rendered from Langfuse."
        ),
        "model": JUDGE_MODEL,
        "calls": calls,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }


def main() -> None:
    price = prices()
    rows = [agent_row(), hw5_row(), hw7_row()]
    for row in rows:
        input_price, output_price = price[row["model"]]
        row["cost_usd"] = round(
            row["input_tokens"] * input_price / 1e6 + row["output_tokens"] * output_price / 1e6, 4
        )
    rows.sort(key=lambda r: r["cost_usd"], reverse=True)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    fields = ["cost_category", "call_site", "purpose", "model", "calls",
              "input_tokens", "output_tokens", "cost_usd"]
    with OUTPUT.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    for row in rows:
        print(f"{row['cost_category']:22s} {row['call_site']:58s} calls={row['calls']:4d} "
              f"in={row['input_tokens']:8d} out={row['output_tokens']:7d} ${row['cost_usd']}")


if __name__ == "__main__":
    main()
