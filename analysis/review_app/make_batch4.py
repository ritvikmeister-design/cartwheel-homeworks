"""Select batch 4: 15 uniform sessions, drawn last, to check taxonomy saturation."""
from __future__ import annotations
import collections, json, pathlib, random
REPO = pathlib.Path(__file__).resolve().parents[2]
STATE = REPO / "analysis" / "state"
rnd = random.Random(1515)

samples = json.loads((STATE/"samples.json").read_text())["samples"]
by_id = {s["session_id"]: s for s in samples}
anns = json.loads((STATE/"annotations.json").read_text())["annotations"]
reviewed = {a["trace_id"] for a in anns}
manifest = json.loads((STATE/"sample_manifest.json").read_text())
entries = {e["session_id"]: e for e in manifest["entries"]}

pool = [s for s in samples if s["session_id"] not in entries and s["session_id"] not in reviewed]
pick = rnd.sample(pool, min(15, len(pool)))
for s in pick:
    entries[s["session_id"]] = {"session_id": s["session_id"], "scenario_id": s["scenario_id"],
        "batch": 4, "method": "uniform_random_saturation_check",
        "reason": "uniform draw taken after the taxonomy was drafted, to measure whether new "
                  "consequential modes still appear"}
manifest["entries"] = [entries[k] for k in sorted(entries, key=lambda k: by_id[k]["scenario_id"])]
(STATE/"sample_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
for s in samples:
    s["batch"] = entries.get(s["session_id"], {}).get("batch")
(STATE/"samples.json").write_text(json.dumps({"samples": samples}, indent=2) + "\n")
print("batch 4 selected:", len(pick))
print("manifest total:", len(entries), dict(sorted(collections.Counter(
    e["batch"] for e in entries.values()).items())))
