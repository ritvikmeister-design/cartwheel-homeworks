"""Part E: one present/absent judgment per (reviewed session, final mode).

Fail  = the session is a confirmed positive for that mode (human annotation or a
        suggestion the human accepted).
Pass  = the session was reviewed and that mode was not observed in it.

Pass-by-default is a recorded inference, not a separate human judgment: the human
read every session in the review set and either marked it clean or wrote what was
wrong, and then worked the per-mode suggestion queue. Suggestions still pending are
listed in the summary because they may understate the modes they belong to.
"""
from __future__ import annotations
import collections, json, pathlib, datetime

REPO = pathlib.Path(__file__).resolve().parents[2]
STATE = REPO / "analysis" / "state"
LAB = STATE / "labels"; LAB.mkdir(parents=True, exist_ok=True)
TS = datetime.datetime.now(datetime.timezone.utc).isoformat()

samples = json.loads((STATE/"samples.json").read_text())["samples"]
by_scen = {s["scenario_id"]: s for s in samples}
A = json.loads((STATE/"annotations.json").read_text())["annotations"]
G = json.loads((STATE/"suggestions.json").read_text())
patterns = json.loads((STATE/"patterns.json").read_text())
modes = patterns["modes"]

reviewed_sessions = {a["trace_id"] for a in A}
reviewed = [s for s in samples if s["session_id"] in reviewed_sessions]
pending = collections.Counter(x["mode"] for x in G if not x.get("status"))

summary = {}
for m in modes:
    pos = set(m["positive_traces"])
    rows = []
    for s in sorted(reviewed, key=lambda x: x["scenario_id"]):
        fail = s["scenario_id"] in pos
        rows.append({"trace_id": s["session_id"], "scenario_id": s["scenario_id"],
                     "label": 1 if fail else 0,
                     "source": "human" if fail else "human_reviewed_not_observed",
                     "ts": TS, "label_id": f"{s['session_id']}#0"})
    path = LAB / f"{m['name']}.jsonl"
    with path.open("w") as fh:
        for r in rows: fh.write(json.dumps(r) + "\n")
    f = sum(r["label"] for r in rows)
    summary[m["name"]] = {"fail": f, "pass": len(rows)-f, "n": len(rows),
                          "sample_fraction": round(f/len(rows), 4),
                          "pending_suggestions": pending.get(m["name"], 0)}

(STATE/"labels_summary.json").write_text(json.dumps(
    {"generated_at": TS, "reviewed_sessions": len(reviewed),
     "note": "Figures are SAMPLE FRACTIONS over a deliberately biased review set "
             "(clustering, stratification and depth searches changed its composition). "
             "They are not prevalence estimates; Homework 5 estimates prevalence over the "
             "full trace store.",
     "modes": summary}, indent=2) + "\n")

print(f"reviewed sessions: {len(reviewed)}  |  modes: {len(modes)}  |  "
      f"judgments: {len(reviewed)*len(modes)}")
print(f"{'mode':34s} {'fail':>5s} {'pass':>5s} {'frac':>7s}  pending")
for n, v in summary.items():
    print(f"{n:34s} {v['fail']:5d} {v['pass']:5d} {v['sample_fraction']:7.3f}  {v['pending_suggestions']}")
print("\nlabel files written to", LAB)
print("files:", sorted(p.name for p in LAB.glob("*.jsonl")))
