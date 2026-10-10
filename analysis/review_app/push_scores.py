"""Write the Part E judgments to Langfuse as scores, one score per (trace, mode).

Cartwheel writes one Langfuse trace per user turn, while a label applies to the
whole session, so each session's label is attached to its first trace, with the
session id recorded in the score comment.
"""
from __future__ import annotations
import json, pathlib, sys, time

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
STATE = REPO/"analysis"/"state"

import os
for line in (REPO/".env").read_text().splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

from analysis.helpers import langfuse_io as lio

if not lio.is_configured():
    raise SystemExit("Langfuse is not configured; check LANGFUSE_* in .env")

samples = {s["session_id"]: s for s in json.loads((STATE/"samples.json").read_text())["samples"]}
modes = [m["name"] for m in json.loads((STATE/"patterns.json").read_text())["modes"]]
client = lio._client()

anchor = {sid: (s["turns"][0]["trace_id"] if s["turns"] else None) for sid, s in samples.items()}
ok = fail = skipped = 0
t0 = time.time()
for mode in modes:
    rows = [json.loads(l) for l in (STATE/"labels"/f"{mode}.jsonl").read_text().splitlines() if l.strip()]
    for r in rows:
        tid = anchor.get(r["trace_id"])
        if not tid:
            skipped += 1; continue
        try:
            client.create_score(name=mode, value=int(r["label"]), trace_id=tid,
                                data_type="NUMERIC",
                                comment=f"session {r['trace_id']} scenario {r['scenario_id']} "
                                        f"source {r['source']}")
            ok += 1
        except Exception as exc:
            fail += 1
            if fail <= 3: print("  error:", type(exc).__name__, str(exc)[:120])
    print(f"  {mode:34s} queued {len(rows)}")
client.flush()
print(f"\nscores queued: {ok}  failed: {fail}  skipped: {skipped}  in {time.time()-t0:.1f}s")
