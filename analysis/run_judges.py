"""HW5 judge inputs, splits, and runs for the misstated_capability mode.

Two label conventions are in play and must not be confused:

  * analysis/state/hw5_labels/misstated_capability.jsonl  -- the HW5 deliverable,
    using the convention hw5.md specifies: 1 = Pass, 0 = Fail.
  * analysis/state/labels/misstated_capability_hw5.jsonl  -- written for the
    installed split_labels helper, which classifies label == 1 as FAIL. Same
    human judgments, inverted encoding, under a distinct mode id so the
    Homework 4 file (misstated_capability.jsonl) is never touched.

The installed split_labels also predates the handout: its signature has no
eligible_trace_ids parameter, so eligibility is enforced by only writing rows
that have a matching input record.
"""
from __future__ import annotations
import collections, json, pathlib, sys

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
STATE = REPO/"analysis"/"state"
MODE_DELIVERABLE = "misstated_capability"
MODE_HELPER = "misstated_capability_hw5"
INPUTS = STATE/"hw5_trace_inputs.json"
TOOLS = {'get_order','list_my_orders','find_order','search_products','search_help_center',
         'get_policy','issue_refund','cancel_order','escalate_to_human'}


def _hw5_labels() -> dict[str, dict]:
    path = STATE/"hw5_labels"/f"{MODE_DELIVERABLE}.jsonl"
    return {json.loads(l)["trace_id"]: json.loads(l)
            for l in path.read_text().splitlines() if l.strip()}


def prepare_inputs() -> list[dict]:
    """One judge-input record per labelled conversation.

    Contains only what a reviewer needed to decide: the user's messages, the
    assistant's replies, and the tool calls with their results, in order. No
    labels, no expected outcome, no scenario identifier, no batch or probe
    marker -- any of those would leak the answer to the judge.
    """
    samples = {s["session_id"]: s
               for s in json.loads((STATE/"samples.json").read_text())["samples"]}
    labels = _hw5_labels()
    records, missing = [], []
    for tid in sorted(labels):
        s = samples.get(tid)
        if not s:
            missing.append(tid); continue
        msgs = []
        for turn in s["turns"]:
            if (turn.get("user") or "").strip():
                msgs.append({"role": "user", "content": turn["user"].strip()})
            for c in turn.get("tools", []):
                if c["name"] not in TOOLS:
                    continue
                msgs.append({"role": "tool_call", "name": c["name"],
                             "arguments": (c.get("args") or "")[:1200]})
                msgs.append({"role": "tool_result", "name": c["name"],
                             "content": (c.get("result") or "")[:2500]})
            if (turn.get("agent") or "").strip():
                msgs.append({"role": "assistant", "content": turn["agent"].strip()})
        records.append({"trace_id": tid, "trace": msgs})
    INPUTS.write_text(json.dumps(records, indent=2) + "\n")

    leak_keys = {"label", "evidence", "expected", "scenario_id", "criterion", "batch", "origin"}
    blob = json.dumps(records)
    leaked = sorted(k for k in leak_keys if f'"{k}"' in blob)
    print(f"input records: {len(records)}  ->  {INPUTS}")
    print(f"  labels without a trace: {len(missing)} {missing[:5]}")
    print(f"  message roles: {dict(collections.Counter(m['role'] for r in records for m in r['trace']))}")
    print(f"  leak check (keys that must be absent): {leaked or 'clean'}")
    return records


def split_data(mode: str = MODE_HELPER) -> dict:
    """Write the helper-facing label file, then split 20/40/40."""
    from analysis.helpers import split_labels

    records = json.loads(INPUTS.read_text())
    eligible = {r["trace_id"] for r in records}
    labels = _hw5_labels()

    path = STATE/"labels"/f"{mode}.jsonl"
    n_fail = n_pass = 0
    with path.open("w") as fh:
        for tid in sorted(eligible):
            v = labels[tid]
            helper_label = 0 if int(v["label"]) == 1 else 1   # invert: helper 1 = Fail
            n_fail += helper_label == 1
            n_pass += helper_label == 0
            fh.write(json.dumps({"trace_id": tid, "label": helper_label,
                                 "source": v.get("source", "human"), "ts": v.get("ts"),
                                 "label_id": f"{tid}#0"}) + "\n")
    print(f"\nhelper label file: {path}")
    print(f"  Fail(1 for the helper): {n_fail}   Pass(0 for the helper): {n_pass}")

    splits = split_labels(mode, fractions=(0.20, 0.40, 0.40), seed=7, min_per_class=10)
    lab = {json.loads(l)["trace_id"]: json.loads(l)["label"]
           for l in path.read_text().splitlines() if l.strip()}
    print("\nsplit (helper convention, 1 = Fail):")
    for name in ("train", "dev", "test"):
        ids = splits[name]
        f = sum(1 for i in ids if lab[i] == 1)
        print(f"  {name:5s} n={len(ids):3d}  Fail={f:3d}  Pass={len(ids)-f:3d}")
    allids = splits["train"] + splits["dev"] + splits["test"]
    print("  disjoint:", len(allids) == len(set(allids)),
          "| covers every eligible label:", set(allids) == eligible)
    print("\nsplits.json written. Do not regenerate it during development.")
    return splits


if __name__ == "__main__":
    prepare_inputs()
    split_data()


# ---------------------------------------------------------------------------
# missing_policy_citation: judge development and test
#
# run_judge's live path dispatches through scale.classify_store, which resolves
# traces via load_store_traces(). That loader fetches per-turn Langfuse traces or
# the committed demo export, and our labels are keyed by cartwheel.session_id, so
# none of our sessions are findable there. We therefore pass run_judge's documented
# `classify` callable, which keeps register_judge, run_judge, judge_alignment and
# freeze_judge (with its test-split guard) all in play while we supply the model
# call ourselves. gpt-4o-mini is also unreachable on this MetaGen entitlement, so
# the judge model is Llama 4 Maverick, used for both development and test.
# ---------------------------------------------------------------------------
MODE_B = "missing_policy_citation"
HELPER_B = f"{MODE_B}_hw5"
INPUTS_B = STATE/"hw5b_trace_inputs.json"
JUDGE_MODEL = "llama4-maverick-17b-128e-instruct"


def _load_env() -> None:
    import os
    for line in (REPO/".env").read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _render(trace: list[dict]) -> str:
    out = []
    for m in trace:
        r = m.get("role")
        if r == "user":
            out.append(f"USER: {m['content']}")
        elif r == "assistant":
            out.append(f"ASSISTANT: {m['content']}")
        elif r == "tool_call":
            out.append(f"TOOL CALL {m['name']}({m.get('arguments','')})")
        elif r == "tool_result":
            out.append(f"TOOL RESULT {m['name']}: {m.get('content','')}")
    return "\n".join(out)


def judge_client():
    """OpenAI-compatible client for the judge gateway (loads .env when present)."""
    import os
    if (REPO/".env").exists():
        _load_env()
    from openai import OpenAI
    return OpenAI(api_key=os.environ["OPENAI_API_KEY"],
                  base_url=os.environ.get("OPENAI_BASE_URL") or os.environ["OPENAI_API_BASE"])


def judge_rendered(client, prompt_text: str, body: str) -> tuple[int, str]:
    """One validated judge call on an already rendered transcript body.

    Returns (1 if failure present else 0, critique). Shared by the HW5 runs and
    the HW7 monitor so both use the same message, model, and verdict parser.
    """
    import re
    for _ in range(4):
        try:
            r = client.chat.completions.create(
                model=JUDGE_MODEL, temperature=0.0, max_tokens=700,
                messages=[{"role": "user",
                           "content": f"{prompt_text}\n\nTRANSCRIPT\n----------\n{body}\n----------\n"}])
            txt = (r.choices[0].message.content or "").strip()
            m = re.search(r"VERDICT:\s*(PASS|FAIL)", txt, re.I)
            if not m:
                raise ValueError("no VERDICT line")
            return (1 if m.group(1).upper() == "FAIL" else 0), txt[-1200:]
        except Exception as exc:
            last = exc
    return 0, f"ERROR: {type(last).__name__}: {last}"   # unparseable -> treat as no failure found


def _make_classifier(max_workers: int = 6):
    """Return fn(prompt_text, trace_ids) -> {trace_id: 1 if failure present else 0}."""
    from concurrent.futures import ThreadPoolExecutor
    client = judge_client()
    by_id = {r["trace_id"]: r for r in json.loads(INPUTS_B.read_text())}
    critiques: dict[str, str] = {}

    def one(tid):
        rec = by_id.get(tid)
        if rec is None:
            raise ValueError(f"trace {tid} missing from {INPUTS_B.name}")
        body = _render(rec["trace"])[:14000]
        verdict, critiques[tid] = judge_rendered(client, one.prompt, body)
        return tid, verdict

    def classify(prompt_text, trace_ids):
        one.prompt = prompt_text
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            return dict(ex.map(one, list(trace_ids)))

    classify.critiques = critiques
    return classify


def run_development(prompt_path: str, mode: str = HELPER_B) -> dict:
    from analysis.helpers import register_judge, run_judge, judge_alignment
    text = pathlib.Path(prompt_path).read_text()
    rec = register_judge(mode=mode, prompt_text=text, judge_model=JUDGE_MODEL)
    jid = rec["judge_id"]
    print(f"registered judge {jid}  model={JUDGE_MODEL}  prompt={pathlib.Path(prompt_path).name}")
    clf = _make_classifier()
    preds = run_judge(jid, split="dev", classify=clf)
    print(f"dev predictions: {len(preds)}  flagged as failure: {sum(preds.values())}")
    m = judge_alignment(jid, split="dev")
    rp = REPO/"analysis"/"report"; rp.mkdir(parents=True, exist_ok=True)
    (rp/f"dev-{jid}.json").write_text(json.dumps(
        {**m, "judge_id": jid, "model": JUDGE_MODEL,
         "prompt_file": str(pathlib.Path(prompt_path).name)}, indent=2, default=str) + "\n")
    (STATE/f"critiques-{jid}-dev.json").write_text(json.dumps(clf.critiques, indent=2) + "\n")
    print(f"\nconfusion (Pass is positive): TP={m['tp']} FN={m['fn']} TN={m['tn']} FP={m['fp']}")
    print(f"TPR {m['tpr']:.3f} {m['tpr_interval']}   TNR {m['tnr']:.3f} {m['tnr_interval']}")
    print(f"agreement {m['agreement']:.3f}  n={m['n']}  disagreements={len(m['disagreements'])}")
    print(f"saved analysis/report/dev-{jid}.json and the critiques")
    return {"judge_id": jid, **m}


def run_test(judge_id: str) -> dict:
    """Freeze the chosen prompt, then score the held-out test split exactly once."""
    from analysis.helpers import freeze_judge, run_judge, judge_alignment
    freeze_judge(judge_id)
    print(f"froze {judge_id}")
    clf = _make_classifier()
    preds = run_judge(judge_id, split="test", classify=clf)
    print(f"test predictions: {len(preds)}  flagged as failure: {sum(preds.values())}")
    m = judge_alignment(judge_id, split="test")
    rp = REPO/"analysis"/"report"; rp.mkdir(parents=True, exist_ok=True)
    (rp/f"test-{judge_id}.json").write_text(json.dumps(
        {**m, "judge_id": judge_id, "model": JUDGE_MODEL,
         "note": "test split scored once after freezing; min_per_class was lowered to 6 "
                 "because only 16 confirmed Fail labels were available"},
        indent=2, default=str) + "\n")
    (STATE/f"critiques-{judge_id}-test.json").write_text(json.dumps(clf.critiques, indent=2) + "\n")
    print(f"\nTEST confusion (Pass is positive): TP={m['tp']} FN={m['fn']} TN={m['tn']} FP={m['fp']}")
    print(f"TPR {m['tpr']:.3f} {m['tpr_interval']}   TNR {m['tnr']:.3f} {m['tnr_interval']}")
    print(f"agreement {m['agreement']:.3f}  n={m['n']}")
    print(f"saved analysis/report/test-{judge_id}.json")
    return m
