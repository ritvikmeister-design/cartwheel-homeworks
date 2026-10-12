"""Export the HW5 probe traces and append them to the labelling queue."""
from __future__ import annotations
import collections, json, pathlib, subprocess, sys

REPO = pathlib.Path(__file__).resolve().parents[2]
STATE = REPO/"analysis"/"state"

out = REPO/"traces"/"hw5_traces.json"
r = subprocess.run([sys.executable, "-m", "scenarios.export_langfuse",
                    "scenarios/hw5_scenarios.jsonl", str(out)],
                   cwd=REPO, capture_output=True, text=True)
print(r.stdout.strip() or r.stderr.strip()[:400])
if not out.exists():
    sys.exit("export failed")

src = (REPO/"analysis"/"review_app"/"build_samples.py").read_text()
exec(src.split("# ---------- load ----------")[0])

export = json.load(open(out))
plan = {json.loads(l)["id"]: json.loads(l)
        for l in (REPO/"scenarios/hw5_scenarios.jsonl").read_text().splitlines() if l.strip()}
results = {json.loads(l)["scenario_id"]: json.loads(l)
           for l in (REPO/"scenarios/hw5-results.jsonl").read_text().splitlines() if l.strip()}

by_session = collections.defaultdict(list)
for tr in export["traces"]:
    a = _attrs(tr)
    if a.get("cartwheel.session_id"):
        by_session[a["cartwheel.session_id"]].append(tr)

new = []
for sid, trs in by_session.items():
    trs.sort(key=lambda x: x.get("createdAt") or "")
    scen = _attrs(trs[0]).get("cartwheel.scenario_id")
    if scen not in plan: continue
    p = plan[scen]; t = p["tuple"]
    turns = []
    for i, tr in enumerate(trs, 1):
        obs = tr.get("observations") or []
        calls = [{"name": o["name"], "args": _text(o.get("input"), 1200),
                  "result": _text(o.get("output"), 2500), "level": o.get("level")}
                 for o in obs if isinstance(o, dict) and o.get("name") in TOOLS]
        turns.append({"n": i, "trace_id": tr.get("id"), "html_path": tr.get("htmlPath"),
                      "user": _text(tr.get("input"), 2000), "agent": _text(tr.get("output"), 6000),
                      "tools": calls, "span_count": len(obs), "latency": tr.get("latency")})
    new.append({"session_id": sid, "scenario_id": scen, "scenario_group": p["scenario_group"],
        "data_quality_case_id": None, "role": t["role"], "user_id": t["user_id"],
        "intent": t["intent"], "difficulty": t["difficulty"], "user_style": t["user_style"],
        "turn_count": t["turn_count"], "tools_needed": t["tools_needed"],
        "applicable_policy": t.get("applicable_policy"),
        "prompt_version": _attrs(trs[0]).get("cartwheel.prompt_version"),
        "model": results.get(scen, {}).get("model"),
        "duration_s": results.get(scen, {}).get("duration_s"),
        "expected": p["expected"], "record": record_for(t), "policy_text": {}, "spec_text": {},
        "turns": turns, "tool_names": [c["name"] for tn in turns for c in tn["tools"]],
        "batch": "hw5_probe", "cluster": -1, "xy": [0, 0]})
print("new probe sessions:", len(new))

S = json.loads((STATE/"samples.json").read_text())["samples"]
have = {s["scenario_id"] for s in S}
S += [n for n in new if n["scenario_id"] not in have]
(STATE/"samples.json").write_text(json.dumps({"samples": S}, indent=2) + "\n")

cand = json.loads((STATE/"hw5_candidates.json").read_text())
cand_src = REPO/"analysis"/"review_app"/"build_hw5_candidates.py"
ns = {"__file__": str(cand_src), "__name__": "_cand"}
exec(cand_src.read_text().split("\nhits = ")[0], ns)
build = ns["build"]
existing = {c["scenario_id"] for c in cand["candidates"]}
added = [build(n) for n in new if n["scenario_id"] not in existing]
cand["candidates"] = sorted(cand["candidates"] + added, key=lambda c: c["scenario_id"])
(STATE/"hw5_candidates.json").write_text(json.dumps(cand, indent=2) + "\n")

L = json.loads((STATE/"hw5_labels.json").read_text())
print("candidates now:", len(cand["candidates"]), "| newly added:", len(added))
print("with a capability claim among the new:", sum(1 for c in added if c["claims"]))
print("already labelled:", len(L), "| still to label:",
      sum(1 for c in cand["candidates"] if c["scenario_id"] not in L))
