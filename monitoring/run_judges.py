"""Run a frozen Homework 5 judge over sampled traces.

This is the expensive track of the two-track plan: the judge runs only on the
plan `monitoring/sample.py` produced, as a batch job off the serving path.

Each trace dict needs "id" and "text". The text is the conversation rendered
exactly as the Homework 5 judge saw it (see `monitoring.run.render_text`).
The frozen judge `missing_policy_citation_hw5-v1` was validated through the
direct gateway call in `analysis/run_judges.py`, not through DocETL, so this
module reuses that call: the same message layout, model, temperature, token
limit, retries, and VERDICT parser.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any

from analysis.helpers.tools import _load_judge, _prompt_hash, _test_labels_and_preds
from analysis.run_judges import JUDGE_MODEL, judge_client, judge_rendered

# The Homework 5 runner truncated each rendered transcript to this length.
MAX_TRANSCRIPT_CHARS = 14000


def load_monitoring_judge(judge_id: str) -> dict[str, Any]:
    """Load the exact frozen judge selected for monitoring."""
    judge = _load_judge(judge_id)
    if judge.get("status") != "frozen":
        raise ValueError(f"judge {judge_id!r} is not frozen")
    if _prompt_hash(judge["prompt_text"], judge["model"]) != judge["prompt_hash"]:
        raise ValueError(f"judge {judge_id!r} prompt or model no longer matches its hash")
    if judge["model"] != JUDGE_MODEL:
        raise ValueError(
            f"judge {judge_id!r} uses {judge['model']!r}, but the validated call path "
            f"uses {JUDGE_MODEL!r}"
        )
    return judge


def judge_test_data(judge_id: str) -> tuple[list[int], list[int]]:
    """Return failure-positive human labels and predictions for correction."""
    return _test_labels_and_preds(load_monitoring_judge(judge_id))


def judge_sample_with_critiques(
    judge_id: str, traces: list[dict[str, Any]], max_workers: int = 6
) -> tuple[dict[str, int], dict[str, str]]:
    """Run the frozen judge and also return each critique (or call error)."""
    if not traces:
        raise ValueError("no traces to judge")
    trace_ids = [str(trace.get("id", "")) for trace in traces]
    if any(not trace_id for trace_id in trace_ids) or len(set(trace_ids)) != len(trace_ids):
        raise ValueError("traces need nonempty, unique ids")
    if any(not str(trace.get("text", "")).strip() for trace in traces):
        raise ValueError("every trace needs normalized conversation text")

    judge = load_monitoring_judge(judge_id)
    client = judge_client()

    def one(trace: dict[str, Any]) -> tuple[str, int, str]:
        body = str(trace["text"])[:MAX_TRANSCRIPT_CHARS]
        verdict, critique = judge_rendered(client, judge["prompt_text"], body)
        return str(trace["id"]), verdict, critique

    verdicts: dict[str, int] = {}
    critiques: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        for trace_id, verdict, critique in pool.map(one, traces):
            verdicts[trace_id] = verdict
            critiques[trace_id] = critique
    return verdicts, critiques


def judge_sample(judge_id: str, traces: list[dict[str, Any]]) -> dict[str, int]:
    """Run the exact frozen judge over the sampled traces.

    Returns trace_id -> 0/1 verdict in the failure-positive convention the
    whole course uses (1 = the failure is present, i.e. the judge said
    "fail"). Requires the judge gateway key.
    """
    return judge_sample_with_critiques(judge_id, traces)[0]
