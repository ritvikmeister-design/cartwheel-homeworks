"""Select the HW4 review batches and record the method and reason for each session.

Batch 1  15 uniform + 15 cluster representatives (breadth)
Batch 2  30 spread across the chosen product dimension, picked before looking at outcomes
Batch 3  25 from depth searches, selected later once candidate modes exist
Batch 4  15 uniform, selected last, to check whether new modes still appear

Batches never overlap. Writes analysis/state/sample_manifest.json and stamps a
`batch` field onto analysis/state/samples.json so the interface can filter by batch.
"""
from __future__ import annotations
import collections, json, pathlib, random, sys

REPO = pathlib.Path(__file__).resolve().parents[2]
STATE = REPO / "analysis" / "state"
DIMENSION = sys.argv[1] if len(sys.argv) > 1 else "role"
rnd = random.Random(40404)

data = json.loads((STATE / "samples.json").read_text())
samples = data["samples"]
samples.sort(key=lambda s: s["scenario_id"])
by_id = {s["session_id"]: s for s in samples}

manifest_path = STATE / "sample_manifest.json"
manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
entries = {e["session_id"]: e for e in manifest.get("entries", [])}
taken = set(entries)

def add(sess, batch, method, reason):
    entries[sess] = {"session_id": sess, "scenario_id": by_id[sess]["scenario_id"],
                     "batch": batch, "method": method, "reason": reason}
    taken.add(sess)

# ---- batch 1a: 15 uniform ----
pool = [s for s in samples if s["session_id"] not in taken]
for s in rnd.sample(pool, 15):
    add(s["session_id"], 1, "uniform_random",
        "uniform draw over all 250 sessions, so the batch is not shaped by any heuristic")

# ---- batch 1b: 15 cluster representatives ----
clusters = collections.defaultdict(list)
for s in samples:
    if s["session_id"] not in taken:
        clusters[s["cluster"]].append(s)
reps, order = [], sorted(clusters, key=lambda c: -len(clusters[c]))
while len(reps) < 15 and order:
    for c in list(order):
        if len(reps) >= 15: break
        if not clusters[c]:
            order.remove(c); continue
        reps.append((c, clusters[c].pop(rnd.randrange(len(clusters[c])))))
for c, s in reps:
    add(s["session_id"], 1, "cluster_representative",
        f"representative of cluster {c} (k-means over turn count, tool-call count, distinct tools, "
        f"role, write-tool presence, reply length, challenge flag)")

# ---- batch 2: 30 across the chosen dimension ----
vals = collections.defaultdict(list)
for s in samples:
    if s["session_id"] not in taken:
        vals[s.get(DIMENSION)].append(s)
keys = sorted(vals, key=lambda k: str(k))
per = max(1, 30 // max(1, len(keys)))
chosen = []
for k in keys:
    chosen += rnd.sample(vals[k], min(per, len(vals[k])))
leftovers = [s for k in keys for s in vals[k] if s not in chosen]
rnd.shuffle(leftovers)
chosen += leftovers[:max(0, 30 - len(chosen))]
for s in chosen[:30]:
    add(s["session_id"], 2, f"dimension_{DIMENSION}",
        f"stratified on {DIMENSION}={s.get(DIMENSION)!r}; the dimension was fixed before any "
        f"outcome was inspected")

manifest = {"dimension_chosen_before_outcomes": DIMENSION,
            "batch_plan": {"1": "15 uniform + 15 cluster representatives",
                           "2": f"30 stratified on {DIMENSION}",
                           "3": "25 from depth searches (selected after candidate modes exist)",
                           "4": "15 uniform (selected last, saturation check)"},
            "entries": [entries[k] for k in sorted(entries, key=lambda k: by_id[k]["scenario_id"])]}
manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

for s in samples:
    s["batch"] = entries.get(s["session_id"], {}).get("batch")
(STATE / "samples.json").write_text(json.dumps({"samples": samples}, indent=2) + "\n")

cnt = collections.Counter(e["batch"] for e in entries.values())
print("manifest entries:", len(entries), dict(sorted(cnt.items())))
print("methods:", dict(collections.Counter(e["method"] for e in entries.values())))
b12 = [by_id[e["session_id"]] for e in entries.values()]
print("roles in review set:", dict(collections.Counter(s["role"] for s in b12)))
print("groups:", dict(collections.Counter(s["scenario_group"] for s in b12)))
print("clusters covered:", sorted({s["cluster"] for s in b12}))
print("overlap check (sessions counted twice):", len(entries) - len({e["session_id"] for e in entries.values()}))
