"""Model cascade for the missing_policy_citation judge (Homework 9 Part D).

The oracle is the frozen Homework 5 judge ``missing_policy_citation_hw5-v1``
(Llama 4 Maverick); its verdicts on the Homework 5 development and test
labels are already saved on the judge record, so it is not called again.
The proxy is Llama 4 Scout with the same prompt, the same rendered transcript,
the same request settings and VERDICT parser, plus one instruction asking for
a confidence from 0 to 1.

Usage:
    uv run python cascade/run_proxy.py run --split dev
    uv run python cascade/run_proxy.py thresholds
    uv run python cascade/run_proxy.py check --threshold T
    uv run python cascade/run_proxy.py run --split test   (before check)

All verdicts use the failure-positive convention: 1 means the failure is
present.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from analysis.run_judges import _render, judge_client  # noqa: E402

STATE = REPO_ROOT / "analysis" / "state"
RESULTS = REPO_ROOT / "cascade" / "results"
ORACLE_ID = "missing_policy_citation_hw5-v1"
ORACLE_MODEL = "openai/llama4-maverick-17b-128e-instruct"
PROXY_MODEL = "openai/llama4-scout-17b-16e-instruct"
REQUIREMENT_PATH = REPO_ROOT / "cascade" / "requirement.json"
THRESHOLDS = [0.0, 0.5, 0.6, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 1.0]
MAX_TRANSCRIPT_CHARS = 14000

CONFIDENCE_INSTRUCTION = (
    "\n\nAfter the VERDICT line, add one more line in exactly this form:\n"
    "CONFIDENCE: <a number from 0 to 1 for how confident you are in your verdict>"
)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text())


def oracle_judge() -> dict[str, Any]:
    return load_json(STATE / "judges" / f"{ORACLE_ID}.json")


def split_ids(split: str) -> list[str]:
    return list(load_json(STATE / "splits.json")[oracle_judge()["mode"]][split])


def human_labels() -> dict[str, int]:
    """Failure-positive human labels, latest live record per trace."""
    labels: dict[str, int] = {}
    path = STATE / "labels" / f"{oracle_judge()['mode']}.jsonl"
    for line in path.read_text().splitlines():
        if line.strip():
            row = json.loads(line)
            if not row.get("superseded_by"):
                labels[row["trace_id"]] = int(row["label"])
    return labels


def oracle_verdicts() -> dict[str, int]:
    judge = oracle_judge()
    return {tid: int(v) for tid, v in judge["predictions"][judge["prompt_hash"]].items()}


def prices() -> dict[str, tuple[float, float]]:
    config = load_json(REPO_ROOT / "optimize" / "config.json")
    return {m: (float(p["input"]), float(p["output"]))
            for m, p in config["prices_per_million_tokens_usd"].items()}


def proxy_call(client: Any, prompt: str, body: str) -> dict[str, Any]:
    """One proxy request: the oracle's message layout and settings on Scout."""
    content = f"{prompt}{CONFIDENCE_INSTRUCTION}\n\nTRANSCRIPT\n----------\n{body}\n----------\n"
    last: Exception | None = None
    for _ in range(4):
        try:
            response = client.chat.completions.create(
                model=PROXY_MODEL.removeprefix("openai/"), temperature=0.0, max_tokens=700,
                messages=[{"role": "user", "content": content}],
            )
            text = (response.choices[0].message.content or "").strip()
            verdict = re.search(r"VERDICT:\s*(PASS|FAIL)", text, re.I)
            if not verdict:
                raise ValueError("no VERDICT line")
            confidence = re.search(r"CONFIDENCE:\s*([01](?:\.\d+)?|\.\d+)", text, re.I)
            usage = response.usage
            return {
                "verdict": 1 if verdict.group(1).upper() == "FAIL" else 0,
                "confidence": min(1.0, float(confidence.group(1))) if confidence else 0.0,
                "confidence_parsed": confidence is not None,
                "input_tokens": usage.prompt_tokens if usage else None,
                "output_tokens": usage.completion_tokens if usage else None,
                "critique": text[-600:],
            }
        except Exception as exc:  # noqa: BLE001 - recorded below
            last = exc
    # Like the oracle, an unparseable answer counts as no failure; zero
    # confidence sends it to the oracle at any threshold above zero.
    return {"verdict": 0, "confidence": 0.0, "confidence_parsed": False,
            "input_tokens": None, "output_tokens": None,
            "critique": f"ERROR: {type(last).__name__}"}


def run(split: str) -> None:
    inputs = {r["trace_id"]: r for r in load_json(STATE / "hw5b_trace_inputs.json")}
    prompt = oracle_judge()["prompt_text"]
    ids = split_ids(split)
    client = judge_client()

    def one(trace_id: str) -> tuple[str, dict[str, Any]]:
        body = _render(inputs[trace_id]["trace"])[:MAX_TRANSCRIPT_CHARS]
        return trace_id, proxy_call(client, prompt, body)

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = dict(pool.map(one, ids))
    RESULTS.mkdir(parents=True, exist_ok=True)
    out = RESULTS / f"proxy-{split}.json"
    out.write_text(json.dumps({"split": split, "proxy_model": PROXY_MODEL,
                               "oracle": ORACLE_ID, "results": results}, indent=2) + "\n")
    errors = sum(1 for r in results.values() if r["critique"].startswith("ERROR"))
    print(f"proxy on {split}: {len(results)} verdicts, {errors} call errors, "
          f"{sum(not r['confidence_parsed'] for r in results.values())} without a confidence -> {out}")


def per_call_costs(results: dict[str, dict[str, Any]]) -> tuple[float, float]:
    """Mean USD per verdict for the proxy (measured) and the oracle (estimated).

    The proxy's token counts come from the API. The oracle was not rerun, so
    its request is estimated from the proxy's: the same message without the
    confidence instruction (Scout and Maverick share the Llama 4 tokenizer),
    and the same number of output tokens.
    """
    price = prices()
    measured = [r for r in results.values() if r["input_tokens"] is not None]
    mean_in = sum(r["input_tokens"] for r in measured) / len(measured)
    mean_out = sum(r["output_tokens"] for r in measured) / len(measured)
    import tiktoken

    # tiktoken approximates the Llama tokenizer for this short instruction.
    instruction_tokens = len(tiktoken.get_encoding("cl100k_base").encode(CONFIDENCE_INSTRUCTION))
    p_in, p_out = price[PROXY_MODEL]
    o_in, o_out = price[ORACLE_MODEL]
    proxy = mean_in * p_in / 1e6 + mean_out * p_out / 1e6
    oracle = (mean_in - instruction_tokens) * o_in / 1e6 + mean_out * o_out / 1e6
    return proxy, oracle


def evaluate(results: dict[str, dict[str, Any]], threshold: float) -> dict[str, Any]:
    oracle, humans = oracle_verdicts(), human_labels()
    ids = list(results)
    cascade = {tid: results[tid]["verdict"] if results[tid]["confidence"] >= threshold
               else oracle[tid] for tid in ids}
    handled = sum(1 for tid in ids if results[tid]["confidence"] >= threshold)
    proxy_cost, oracle_cost = per_call_costs(results)
    share = handled / len(ids)
    return {
        "threshold": threshold,
        "examples": len(ids),
        "agreement_with_oracle": round(sum(cascade[t] == oracle[t] for t in ids) / len(ids), 4),
        "disagreements_with_oracle": sum(cascade[t] != oracle[t] for t in ids),
        "agreement_with_human_labels": round(sum(cascade[t] == humans[t] for t in ids) / len(ids), 4),
        "proxy_share": round(share, 4),
        # Every verdict pays for the proxy; the oracle runs only when the
        # proxy is below the threshold.
        "cost_per_1000_verdicts_usd": round(1000 * (proxy_cost + (1 - share) * oracle_cost), 4),
        "oracle_only_cost_per_1000_verdicts_usd": round(1000 * oracle_cost, 4),
    }


def thresholds() -> None:
    results = load_json(RESULTS / "proxy-dev.json")["results"]
    rows = [evaluate(results, t) for t in THRESHOLDS]
    fields = ["threshold", "agreement_with_oracle", "agreement_with_human_labels",
              "proxy_share", "cost_per_1000_verdicts_usd"]
    with (RESULTS / "thresholds.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    requirement = load_json(REQUIREMENT_PATH)["minimum_agreement_with_oracle"]
    for row in rows:
        print(row)
    meeting = [r["threshold"] for r in rows if r["agreement_with_oracle"] >= requirement]
    print(f"lowest threshold meeting {requirement}: {min(meeting) if meeting else 'none'}")


def check(threshold: float) -> None:
    out = RESULTS / "check.json"
    if out.exists():
        raise SystemExit(f"{out} exists; the threshold is checked once")
    results = load_json(RESULTS / "proxy-test.json")["results"]
    requirement = load_json(REQUIREMENT_PATH)["minimum_agreement_with_oracle"]
    summary = evaluate(results, threshold)
    summary.update({
        "split": "test",
        "minimum_agreement_with_oracle": requirement,
        "meets_requirement": summary["agreement_with_oracle"] >= requirement,
        "proxy_model": PROXY_MODEL,
        "oracle": ORACLE_ID,
    })
    out.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    run_parser = sub.add_parser("run")
    run_parser.add_argument("--split", choices=["dev", "test"], required=True)
    sub.add_parser("thresholds")
    check_parser = sub.add_parser("check")
    check_parser.add_argument("--threshold", type=float, required=True)
    args = parser.parse_args()
    if args.command == "run":
        run(args.split)
    elif args.command == "thresholds":
        thresholds()
    else:
        check(args.threshold)


if __name__ == "__main__":
    main()
