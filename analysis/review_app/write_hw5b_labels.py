"""Write labels, judge inputs and splits for missing_policy_citation."""
from __future__ import annotations
import collections, datetime, json, pathlib, sys

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
STATE = REPO/"analysis"/"state"
MODE = "missing_policy_citation"
HELPER = f"{MODE}_hw5"
TS = datetime.datetime.now(datetime.timezone.utc).isoformat()
TOOLS = {'get_order','list_my_orders','find_order','search_products','search_help_center',
         'get_policy','issue_refund','cancel_order','escalate_to_human'}

FAILS = {"final-036","final-038","final-041","final-042","final-044","final-047","final-050",
         "final-052","final-053","final-056","final-058","final-105","final-015","final-181",
         "final-217","hw5-037"}

cand = json.loads((STATE/"hw5b_candidates.json").read_text())["candidates"]
S = {s["session_id"]: s for s in json.loads((STATE/"samples.json").read_text())["samples"]}

rows = []
for c in cand:
    scen = c["scenario_id"]
    fail = scen in FAILS
    if fail:
        ev = ("policy-derived claim with no identifier: "
              + " | ".join(cl["text"][:150] for cl in c["claims"][:2]))
        src = "human"
    elif c["group"] == "C":
        ev = ("the only policy-shaped figure is the escalation SLA, which escalate_to_human "
              "returns as sla_hours, so it is record-derived rather than policy-derived")
        src = "human_ratified_signal"
    elif c["group"] == "B":
        ev = f"identifier(s) cited in the reply: {', '.join(c['citations_found'])}"
        src = "human_ratified_signal"
    else:
        ev = "no policy-derived claim detected in the reply"
        src = "human_ratified_signal"
    rows.append({"trace_id": c["session_id"], "scenario_id": scen,
                 "label": 0 if fail else 1, "source": src, "evidence": ev[:600],
                 "ts": TS, "label_id": f'{c["session_id"]}#0',
                 "group": c["group"], "suggested": c["suggested"],
                 "overrode_signal": (0 if fail else 1) != c["suggested"]})

out = STATE/"hw5_labels"/f"{MODE}.jsonl"
with out.open("w") as fh:
    for r in rows: fh.write(json.dumps(r, ensure_ascii=False) + "\n")
cc = collections.Counter(r["label"] for r in rows)
print("deliverable:", out.name, "| Pass(1):", cc[1], "| Fail(0):", cc[0])
print("overrode the mechanical signal:", sum(1 for r in rows if r["overrode_signal"]),
      "of", len(rows))

# helper-facing file: 1 = Fail
hp = STATE/"labels"/f"{HELPER}.jsonl"
with hp.open("w") as fh:
    for r in rows:
        fh.write(json.dumps({"trace_id": r["trace_id"], "label": 0 if r["label"] == 1 else 1,
                             "source": r["source"], "ts": TS,
                             "label_id": r["label_id"]}) + "\n")

# judge inputs for exactly these sessions, no labels or metadata
recs = []
for r in rows:
    s = S[r["trace_id"]]
    msgs = []
    for t in s["turns"]:
        if (t.get("user") or "").strip():
            msgs.append({"role": "user", "content": t["user"].strip()})
        for c2 in t.get("tools", []):
            if c2["name"] in TOOLS:
                msgs.append({"role": "tool_call", "name": c2["name"],
                             "arguments": (c2.get("args") or "")[:1200]})
                msgs.append({"role": "tool_result", "name": c2["name"],
                             "content": (c2.get("result") or "")[:2500]})
        if (t.get("agent") or "").strip():
            msgs.append({"role": "assistant", "content": t["agent"].strip()})
    recs.append({"trace_id": r["trace_id"], "trace": msgs})
ip = STATE/"hw5b_trace_inputs.json"
ip.write_text(json.dumps(recs, indent=2) + "\n")
blob = json.dumps(recs)
leaks = [k for k in ("label","evidence","scenario_id","group","suggested") if f'"{k}"' in blob]
print("judge inputs:", len(recs), "->", ip.name, "| leak check:", leaks or "clean")

from analysis.helpers import split_labels
for mpc in (10, 8, 6, 5):
    try:
        sp = split_labels(HELPER, fractions=(0.20, 0.40, 0.40), seed=7, min_per_class=mpc)
        lab = {json.loads(l)["trace_id"]: json.loads(l)["label"]
               for l in hp.read_text().splitlines() if l.strip()}
        print(f"\nsplit accepted at min_per_class={mpc}")
        for nm in ("train","dev","test"):
            ids = sp[nm]; f = sum(1 for i in ids if lab[i] == 1)
            print(f"  {nm:5s} n={len(ids):3d} Fail={f:3d} Pass={len(ids)-f:3d}")
        break
    except Exception as e:
        print(f"min_per_class={mpc} refused: {type(e).__name__}")
