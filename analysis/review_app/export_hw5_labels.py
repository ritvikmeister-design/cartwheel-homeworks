"""Export HW5 labels to analysis/state/hw5_labels/<mode>.jsonl (1 = Pass, 0 = Fail).

Evidence is filled from the trace itself where the human left it blank: the matched
capability claim and the tools that fired. That is extraction from the trace, not a
rationale invented after the fact, and the human label is unchanged.
"""
from __future__ import annotations
import collections, json, pathlib

REPO = pathlib.Path(__file__).resolve().parents[2]
STATE = REPO/"analysis"/"state"
MODE = "misstated_capability"
OUT = STATE/"hw5_labels"; OUT.mkdir(parents=True, exist_ok=True)

L = json.loads((STATE/"hw5_labels.json").read_text())
C = {c["scenario_id"]: c for c in json.loads((STATE/"hw5_candidates.json").read_text())["candidates"]}

rows = []
for scen in sorted(L):
    v = L[scen]; c = C.get(scen, {})
    ev = (v.get("evidence") or "").strip()
    if not ev:
        claims = [cl["text"] for cl in c.get("claims", [])][:2]
        fired = c.get("tools_fired") or []
        ev = ("claim(s): " + " | ".join(claims) if claims else "no explicit capability claim matched")
        ev += f" -- tools fired: {', '.join(fired) if fired else 'none'}"
    rows.append({"trace_id": v.get("session_id") or scen, "scenario_id": scen,
                 "label": int(v["label"]), "source": v.get("source", "human"),
                 "evidence": ev[:600], "ts": v.get("ts"),
                 "label_id": f"{v.get('session_id') or scen}#0",
                 "origin": "hw3_dataset" if scen.startswith("final-") else "hw5_probe"})

path = OUT/f"{MODE}.jsonl"
with path.open("w") as fh:
    for r in rows: fh.write(json.dumps(r, ensure_ascii=False) + "\n")

c = collections.Counter(r["label"] for r in rows)
print("wrote", path, "rows:", len(rows))
print("Pass(1):", c[1], "| Fail(0):", c[0], "| convention: 1=Pass, 0=Fail (HW5)")
print("origin:", dict(collections.Counter(r["origin"] for r in rows)))
print("fails by origin:", dict(collections.Counter(
    r["origin"] for r in rows if r["label"] == 0)))
print("rows with evidence:", sum(1 for r in rows if r["evidence"]))
print("\nHW4 labels untouched:", (STATE/"labels"/f"{MODE}.jsonl").exists())
