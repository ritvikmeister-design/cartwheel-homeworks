"""Generate user messages for the HW5 capability-probe scenarios and write the JSONL."""
from __future__ import annotations
import collections, json, pathlib, re, sys
from concurrent.futures import ThreadPoolExecutor

REPO = pathlib.Path(__file__).resolve().parents[2]
SRC = (pathlib.Path.home()/"Documents/ai-evals-course/cartwheel-scripts/gen_final_messages.py")
if not SRC.exists():
    sys.exit(f"missing {SRC} - the HW3 generation helper is needed for gen()")
exec(SRC.read_text().split("ROWS = json.loads")[0])   # client, MODEL, TEMP, STYLE, ROLE, parse(), gen()

ASSUMES = re.compile(r"^\s*(?:yes|yep|yeah|ok|okay|sure|no|thanks)\b|"
  r"\b(?:go ahead|do that|that worked|as you said|you just said)\b", re.I)
HARD = [re.compile(r"\b(?:get_order|list_my_orders|find_order|search_products|search_help_center|"
        r"get_policy|issue_refund|cancel_order|escalate_to_human)\b", re.I),
        re.compile(r"\b(?:cw-[a-z-]+|store-[a-z-]+-policy)\b", re.I),
        re.compile(r"\b(?:RESP|ESC|AUTH|SCOPE|TOOL)-\d\b")]

ROWS = {r["id"]: r for r in json.loads((REPO/"scenarios/hw5_plan.json").read_text())}
print("generating", len(ROWS), "conversations with", MODEL)
with ThreadPoolExecutor(max_workers=6) as ex:
    msgs = {m["id"]: m for m in ex.map(gen, [ROWS[k] for k in sorted(ROWS)])}

def problems(sid, m):
    t = ROWS[sid]["tuple"]; xs = [m["opening_message"], *m["followups"]]
    bad = []
    for i, x in enumerate(xs):
        if any(rx.search(x) for rx in HARD): bad.append(f"msg{i}:leak")
        if i > 0 and ASSUMES.search(x): bad.append(f"msg{i}:assumes_reply")
    if "order_id" in t and str(t["order_id"]) not in " ".join(xs):
        bad.append("missing_order_number")
    return bad

def key(m): return " ".join(m["opening_message"].lower().split()[:5])
for attempt in range(4):
    g = collections.defaultdict(list)
    for sid, m in msgs.items():
        if "error" not in m: g[key(m)].append(sid)
    redo = sorted({s for ids in g.values() if len(ids) > 1 for s in ids[1:]}
                  | {s for s, m in msgs.items() if "error" in m or problems(s, m)})
    print(f"attempt {attempt}: fixing {len(redo)}")
    if not redo: break
    for sid in redo:
        row = dict(ROWS[sid])
        row["user_visible_facts"] += (". Open with distinctly different wording from generic "
                                      "support-chat phrasing, and keep every later message standalone")
        new = gen(row)
        if "error" not in new and not problems(sid, new): msgs[sid] = new

bad = {s: problems(s, m) for s, m in msgs.items() if "error" in m or problems(s, m)}
print("remaining problems:", bad or "none")
(REPO/"scenarios/hw5_messages.json").write_text(
    json.dumps([msgs[k] for k in sorted(msgs)], indent=2) + "\n")

rows = []
for sid in sorted(ROWS):
    p, m = ROWS[sid], msgs[sid]
    t = dict(p["tuple"])
    t["turn_count"] = 1 + len(m["followups"])      # trust what was generated
    rows.append({"id": sid, "scenario_group": p["scenario_group"],
                 "data_quality_case_id": p["data_quality_case_id"], "tuple": t,
                 "opening_message": m["opening_message"], "followups": m["followups"],
                 "expected": p["expected"]})
out = REPO/"scenarios/hw5_scenarios.jsonl"
with out.open("w") as fh:
    for r in rows: fh.write(json.dumps(r, ensure_ascii=False) + "\n")
print("wrote", out, "rows:", len(rows))
print("id overlap with HW3:", bool({r['id'] for r in rows} &
      {json.loads(l)['id'] for l in (REPO/'scenarios/support_scenarios.jsonl').read_text().splitlines() if l.strip()}))
