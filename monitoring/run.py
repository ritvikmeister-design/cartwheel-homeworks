"""Run the Homework 7 monitor for one comparison period or a recent window.

Usage:
    uv run python -m monitoring.run --period before
    uv run python -m monitoring.run --period after
    uv run python -m monitoring.run --last-hours 24

A comparison period is a fixed UTC window from ``monitoring/config.json``. It
must contain every scenario in the monitoring set exactly once, as one session
per scenario, and every eligible trace must use the configured Cartwheel model.
A ``--last-hours`` window groups recent traces by ``cartwheel.session_id``.

Each conversation is rendered exactly as the frozen Homework 5 judge saw its
inputs: the turn text and tool evidence follow
``analysis/review_app/build_samples.py`` and ``analysis/run_judges.py``. The
random sample estimates the failure rate; the risk groups are judged in the
same call but kept separate, and only the random verdicts reach the
correction.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from analysis.run_judges import TOOLS, _render
from monitoring.sample import DEFAULT_RISK_GROUPS, select_traces

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "monitoring" / "config.json"
HISTORY_PATH = REPO_ROOT / "monitoring" / "history.jsonl"
CHART_PATH = REPO_ROOT / "monitoring" / "prevalence.svg"
OUTPUT_DIR = REPO_ROOT / "monitoring" / "output"


class PeriodRejected(ValueError):
    """The traces in a window do not form one valid comparison period."""


# ---------------------------------------------------------------------------
# Trace text, matching the Homework 5 judge inputs
# ---------------------------------------------------------------------------


def _text(v: Any, limit: int = 4000) -> str:
    """Flatten a Langfuse input or output value (from build_samples.py)."""
    if v is None:
        return ""
    if isinstance(v, str):
        s = v
    else:
        try:
            if isinstance(v, list):
                parts = []
                for m in v:
                    if isinstance(m, dict):
                        for p in m.get("parts") or []:
                            if isinstance(p, dict) and p.get("content"):
                                parts.append(str(p["content"]))
                        if not m.get("parts") and m.get("content"):
                            parts.append(str(m["content"]))
                s = "\n".join(parts) if parts else json.dumps(v)[:limit]
            else:
                s = json.dumps(v)[:limit]
        except Exception:
            s = str(v)[:limit]
    return s[:limit]


def _attributes(obj: dict[str, Any]) -> dict[str, Any]:
    metadata = obj.get("metadata") or {}
    attributes = metadata.get("attributes") if isinstance(metadata, dict) else None
    if isinstance(attributes, str):
        try:
            attributes = json.loads(attributes)
        except ValueError:
            attributes = {}
    return attributes if isinstance(attributes, dict) else {}


def trace_turn(trace: dict[str, Any]) -> dict[str, Any]:
    """One conversation turn from one Langfuse trace (build_samples.py layout)."""
    calls = [
        {
            "name": o["name"],
            "args": _text(o.get("input"), 1200),
            "result": _text(o.get("output"), 2500),
        }
        for o in trace.get("observations") or []
        if isinstance(o, dict) and o.get("name") in TOOLS
    ]
    return {
        "trace_id": trace.get("id"),
        "user": _text(trace.get("input"), 2000),
        "agent": _text(trace.get("output"), 6000),
        "tools": calls,
    }


def judge_messages(turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The Homework 5 judge message list (analysis/run_judges.prepare_inputs)."""
    messages: list[dict[str, Any]] = []
    for turn in turns:
        if (turn.get("user") or "").strip():
            messages.append({"role": "user", "content": turn["user"].strip()})
        for call in turn.get("tools", []):
            if call["name"] not in TOOLS:
                continue
            messages.append(
                {"role": "tool_call", "name": call["name"],
                 "arguments": (call.get("args") or "")[:1200]}
            )
            messages.append(
                {"role": "tool_result", "name": call["name"],
                 "content": (call.get("result") or "")[:2500]}
            )
        if (turn.get("agent") or "").strip():
            messages.append({"role": "assistant", "content": turn["agent"].strip()})
    return messages


def render_text(turns: list[dict[str, Any]]) -> str:
    """Normalized conversation text: ordered turns and tool evidence only."""
    return _render(judge_messages(turns))


# ---------------------------------------------------------------------------
# Langfuse
# ---------------------------------------------------------------------------


def scenario_id(trace: dict[str, Any]) -> str | None:
    value = (trace.get("metadata") or {}).get("cartwheel.scenario_id") or _attributes(trace).get(
        "cartwheel.scenario_id"
    )
    return str(value) if value else None


def session_id(trace: dict[str, Any]) -> str | None:
    value = _attributes(trace).get("cartwheel.session_id") or trace.get("sessionId")
    return str(value) if value else None


def trace_models(trace: dict[str, Any]) -> set[str]:
    return {
        str(o["model"])
        for o in trace.get("observations") or []
        if isinstance(o, dict) and o.get("type") == "GENERATION" and o.get("model")
    }


def fetch_traces(start: datetime, end: datetime, page_size: int = 100) -> list[dict[str, Any]]:
    """Full Langfuse trace records (with observations) whose timestamp is in [start, end].

    Each record goes through the same JSON round trip as the Homework 3 export
    (``sort_keys=True``), which is the form the Homework 5 judge inputs were
    built from, so tool arguments and results render with the same key order.
    """
    from langfuse import Langfuse

    from scenarios.export_langfuse import _json_default, _jsonable

    client = Langfuse()
    traces: list[dict[str, Any]] = []
    page = 1
    while True:
        response = client.api.trace.list(
            page=page, limit=page_size, from_timestamp=start, to_timestamp=end
        )
        batch = list(response.data or [])
        for summary in batch:
            record = _jsonable(client.api.trace.get(summary.id))
            traces.append(json.loads(json.dumps(record, sort_keys=True, default=_json_default)))
        if len(batch) < page_size:
            break
        page += 1
    return traces


# ---------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------


def build_conversations(groups: dict[str, list[dict[str, Any]]], key: str) -> list[dict[str, Any]]:
    """One conversation record per group, identified by its final trace id."""
    records = []
    for group_key in sorted(groups):
        traces = sorted(groups[group_key], key=lambda t: t.get("createdAt") or t.get("timestamp") or "")
        turns = [trace_turn(trace) for trace in traces]
        records.append(
            {
                "id": traces[-1]["id"],
                key: group_key,
                "session_id": session_id(traces[0]),
                "trace_ids": [trace["id"] for trace in traces],
                "timestamp": traces[-1].get("timestamp"),
                "tools": [call["name"] for turn in turns for call in turn["tools"]],
                "turn_count": sum(1 for turn in turns if turn["user"].strip()),
                "models": sorted({m for trace in traces for m in trace_models(trace)}),
                "text": render_text(turns),
            }
        )
    return records


def period_conversations(
    traces: list[dict[str, Any]], scenario_ids: set[str], model: str
) -> tuple[list[dict[str, Any]], int]:
    """Validate one comparison period and return (conversations, eligible trace count)."""
    by_scenario: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for trace in traces:
        sid = scenario_id(trace)
        if sid in scenario_ids:
            by_scenario[sid].append(trace)
    missing = sorted(scenario_ids - set(by_scenario))
    if missing:
        raise PeriodRejected(f"{len(missing)} scenario ids have no trace in the window: {missing[:5]}")
    retried = sorted(
        sid for sid, group in by_scenario.items() if len({session_id(t) for t in group}) > 1
    )
    if retried:
        raise PeriodRejected(
            f"{len(retried)} scenarios have more than one session (separate retries): {retried[:5]}"
        )
    _check_models([t for group in by_scenario.values() for t in group], model)
    conversations = build_conversations(by_scenario, "scenario_id")
    if len(conversations) != len(scenario_ids):
        raise PeriodRejected(f"expected {len(scenario_ids)} conversations, built {len(conversations)}")
    return conversations, sum(len(group) for group in by_scenario.values())


def window_conversations(traces: list[dict[str, Any]], model: str) -> tuple[list[dict[str, Any]], int]:
    """Group a recent window's traces by cartwheel.session_id."""
    by_session: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for trace in traces:
        sid = session_id(trace)
        if sid:
            by_session[sid].append(trace)
    eligible = [t for group in by_session.values() for t in group]
    _check_models(eligible, model)
    return build_conversations(by_session, "session_id"), len(eligible)


def _check_models(traces: list[dict[str, Any]], model: str) -> None:
    other = sorted({m for trace in traces for m in trace_models(trace)} - {model})
    if other:
        raise PeriodRejected(f"eligible traces use a different Cartwheel model: {other}")


# ---------------------------------------------------------------------------
# History and chart
# ---------------------------------------------------------------------------


def update_history(record: dict[str, Any], periods: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Replace this period's line in history.jsonl, keeping the configured order."""
    rows = []
    if HISTORY_PATH.exists():
        rows = [json.loads(line) for line in HISTORY_PATH.read_text().splitlines() if line.strip()]
    rows = [row for row in rows if row["label"] != record["label"]] + [record]
    order = {period["label"]: index for index, period in enumerate(periods)}
    rows.sort(key=lambda row: order.get(row["label"], len(order)))
    HISTORY_PATH.write_text("".join(json.dumps(row) + "\n" for row in rows))
    return rows


def write_chart(rows: list[dict[str, Any]], threshold: float, mode: str) -> None:
    from monitoring.chart import prevalence_chart

    points = [
        {"label": row["label"], "corrected": row["corrected"],
         "ci_low": row["ci_low"], "ci_high": row["ci_high"]}
        for row in rows
    ]
    CHART_PATH.write_text(prevalence_chart(points, threshold=threshold, mode=mode) + "\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def monitor_session(label: str) -> str:
    """Langfuse session that holds a batch's corrected-prevalence score."""
    return f"hw7-monitor-{label}"


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run(args: argparse.Namespace) -> int:
    from observability.instrument import load_env

    load_env()
    config = json.loads(Path(args.config).read_text())
    judge_id, mode, model = config["judge_id"], config["judge_mode"], config["model"]
    risk_groups = {name: DEFAULT_RISK_GROUPS[name] for name in config["risk_groups"]}

    if args.period:
        period = next((p for p in config["periods"] if p["label"] == args.period), None)
        if period is None:
            raise SystemExit(f"no period {args.period!r} in {args.config}")
        label, start, end = period["label"], _parse_time(period["from"]), _parse_time(period["to"])
    else:
        end = datetime.now(timezone.utc)
        start = end - timedelta(hours=args.last_hours)
        label = f"last{args.last_hours}h-{end.strftime('%Y-%m-%dT%H%MZ')}"

    traces = fetch_traces(start, end)
    if args.period:
        scenario_path = REPO_ROOT / config.get("scenarios", "scenarios/monitoring_scenarios.jsonl")
        scenario_ids = {
            json.loads(line)["id"] for line in scenario_path.read_text().splitlines() if line.strip()
        }
        conversations, n_traces = period_conversations(traces, scenario_ids, model)
    else:
        conversations, n_traces = window_conversations(traces, model)

    summary: dict[str, Any] = {
        "label": label,
        "judge_id": judge_id,
        "judge_mode": mode,
        "model": model,
        "from": _iso(start),
        "to": _iso(end),
        "langfuse_traces_in_window": len(traces),
        "langfuse_traces": n_traces,
        "conversations": len(conversations),
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"{label}.json"

    if not conversations:
        summary.update({"random_sample": 0, "risk_sample": 0, "judge_calls": 0})
        output_path.write_text(json.dumps(summary, indent=2) + "\n")
        print(f"{label}: no eligible conversations between {summary['from']} and {summary['to']}; "
              "recorded a zero count and skipped the judge")
        return 0

    plan = select_traces(conversations, config["random_rate"], risk_groups, seed=config.get("seed", 7))
    random_ids = [c["id"] for c in plan["random"]]
    risk_ids = list(dict.fromkeys(c["id"] for members in plan["risk_groups"].values() for c in members))
    print(f"{label}: {len(traces)} traces in window, {n_traces} eligible, {len(conversations)} conversations")
    print(f"  random sample: {len(random_ids)}; risk groups: "
          + ", ".join(f"{name}={len(members)}" for name, members in plan["risk_groups"].items())
          + f" ({len(risk_ids)} unique)")
    print(f"  judge calls: {len(plan['to_judge'])} with {judge_id}")
    if args.plan_only:
        return 0

    from monitoring.correct import corrected_mode_prevalence
    from monitoring.run_judges import judge_sample_with_critiques, judge_test_data
    from monitoring.write_scores import build_score_records, post_scores

    verdicts, critiques = judge_sample_with_critiques(judge_id, plan["to_judge"])
    random_verdicts = {trace_id: verdicts[trace_id] for trace_id in random_ids}
    risk_verdicts = {trace_id: verdicts[trace_id] for trace_id in risk_ids}
    test_labels, test_preds = judge_test_data(judge_id)
    estimate = corrected_mode_prevalence(list(random_verdicts.values()), test_labels, test_preds)
    records = build_score_records(mode, random_verdicts, risk_verdicts, estimate, label)
    trace_times = {c["id"]: _parse_time(c["timestamp"]) for c in conversations if c.get("timestamp")}
    written = 0 if args.no_scores else post_scores(
        records, session_id=monitor_session(label), trace_times=trace_times, batch_time=end
    )

    summary.update(
        {
            "random_sample": len(random_ids),
            "risk_sample": len(risk_ids),
            "risk_group_sizes": {name: len(m) for name, m in plan["risk_groups"].items()},
            "judge_calls": len(plan["to_judge"]),
            "judge_call_errors": sum(1 for c in critiques.values() if c.startswith("ERROR:")),
            "random_flagged": sum(random_verdicts.values()),
            "risk_flagged": sum(risk_verdicts.values()),
            **{key: estimate[key] for key in (
                "raw", "corrected", "ci_low", "ci_high", "confidence",
                "failure_sensitivity", "pass_specificity", "n_sample")},
            "threshold": config["threshold"],
            "crossed_threshold": estimate["corrected"] > config["threshold"],
            "scores_written": written,
            "ran_at": _iso(datetime.now(timezone.utc)),
        }
    )
    by_id = {c["id"]: c for c in conversations}
    details = [
        {
            "trace_id": trace_id,
            "scenario_id": by_id[trace_id].get("scenario_id"),
            "session_id": by_id[trace_id]["session_id"],
            "timestamp": by_id[trace_id].get("timestamp"),
            "random": trace_id in random_verdicts,
            "risk_groups": [n for n, m in plan["risk_groups"].items() if any(c["id"] == trace_id for c in m)],
            "verdict": verdicts[trace_id],
            "critique": critiques[trace_id],
        }
        for trace_id in verdicts
    ]
    output_path.write_text(json.dumps({**summary, "judged": details}, indent=2) + "\n")

    if args.period:
        rows = update_history(summary, config["periods"])
        write_chart(rows, config["threshold"], mode)
    print(f"  raw {estimate['raw']}, corrected {estimate['corrected']} "
          f"[{estimate['ci_low']}, {estimate['ci_high']}], scores written: {written}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    which = parser.add_mutually_exclusive_group(required=True)
    which.add_argument("--period", help="label of a period in the config")
    which.add_argument("--last-hours", type=int, help="monitor traces from the last N hours")
    parser.add_argument("--config", default=str(CONFIG_PATH))
    parser.add_argument("--plan-only", action="store_true", help="show the sample and stop before judging")
    parser.add_argument("--no-scores", action="store_true", help="skip writing scores to Langfuse")
    args = parser.parse_args(argv)
    try:
        return run(args)
    except PeriodRejected as exc:
        print(f"period rejected: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
