"""Depth searches for candidate failure modes (HW4 Part B batch 3 / Part D).

Every filter here is a RETRIEVAL SIGNAL, never a label. Each hit becomes a
suggestion the human accepts or rejects. Filters deliberately favour recall:
a wrong suggestion costs one click, a missed instance costs coverage.

Also selects batch 3 (25 sessions not already reviewed) spread across the
candidate modes, plus close negatives so each mode's boundary is testable.
"""
from __future__ import annotations
import collections, json, pathlib, random, re

REPO = pathlib.Path(__file__).resolve().parents[2]
STATE = REPO / "analysis" / "state"
rnd = random.Random(909)

samples = json.loads((STATE/"samples.json").read_text())["samples"]
anns = json.loads((STATE/"annotations.json").read_text())["annotations"]
reviewed = {a["trace_id"] for a in anns}
by_id = {s["session_id"]: s for s in samples}

def replies(s): return " \n".join(t["agent"] or "" for t in s["turns"])
def tool_results(s, name=None):
    return [c["result"] or "" for t in s["turns"] for c in t["tools"]
            if name is None or c["name"] == name]
def tool_count(s, name): return sum(1 for n in s["tool_names"] if n == name)
def caller_store(s): return ((s.get("record") or {}).get("caller") or {}).get("store_id")

ASKS = re.compile(r"today'?s date|how long ago|when did you (receive|get)|what(?:'s| is) the date", re.I)
CONFIRM = re.compile(r"just confirm|can you confirm|confirm (?:the|that|whether)", re.I)
YOURS = re.compile(r"\byour (?:order|orders|account|purchase|package|delivery)\b", re.I)
TICKET = re.compile(r"(?:check|track|look up|status of).{0,40}(?:ticket|case|request)|"
                    r"(?:ticket|case).{0,25}(?:status|progress)", re.I)
OFFER = re.compile(r"\bI can also\b|\bwould you like me to\b|\bI could also\b|\bhappy to also\b|"
                   r"\bI can go ahead and\b", re.I)
STORE_N = re.compile(r'"store_id":\s*(\d+)|\bStore (\d+)\b')

def hits_tool_result_not_used(s):
    got = any('"refund_eligible": true' in r.lower() or '"refund_eligible":true' in r.lower()
              for r in tool_results(s, "get_order"))
    if not got: return None
    r = replies(s)
    m = ASKS.search(r) or CONFIRM.search(r)
    if not m: return None
    return f"get_order returned refund_eligible true and the reply still asks: '{m.group(0)}'"

def hits_role_blind(s):
    if s["role"] != "support": return None
    m = YOURS.search(replies(s))
    return f"support caller addressed with '{m.group(0)}'" if m else None

def hits_cross_store(s):
    if s["role"] != "merchant": return None
    own = caller_store(s)
    if own is None: return None
    seen = set()
    for r in tool_results(s, "search_products"):
        for a, b in STORE_N.findall(r):
            v = a or b
            if v: seen.add(int(v))
    other = sorted(seen - {own})
    return f"merchant owns store {own}; search_products results mention store(s) {other}" if other else None

def hits_capability_claim(s):
    m = TICKET.search(replies(s))
    if not m: return None
    return f"reply references ticket/case status ('{m.group(0)[:60]}') but no tool exposes it"

def hits_duplicate_escalation(s):
    n = tool_count(s, "escalate_to_human")
    return f"escalate_to_human called {n} times in one session" if n >= 2 else None

def hits_unsolicited_offer(s):
    m = OFFER.search(replies(s))
    return f"reply volunteers an extra action: '{m.group(0)}'" if m else None

FILTERS = {
    "tool_result_not_used": hits_tool_result_not_used,
    "role_blind_reply": hits_role_blind,
    "cross_store_results_to_merchant": hits_cross_store,
    "capability_claim_without_tool": hits_capability_claim,
    "duplicate_escalation": hits_duplicate_escalation,
    "unsolicited_action_offer": hits_unsolicited_offer,
}
# close-negative probes: superficially similar, expected to be clean
NEGATIVES = {
    "role_blind_reply": lambda s: s["role"] == "support" and not YOURS.search(replies(s)),
    "cross_store_results_to_merchant": lambda s: (s["role"] == "merchant"
        and "search_products" in s["tool_names"] and not hits_cross_store(s)),
    "duplicate_escalation": lambda s: tool_count(s, "escalate_to_human") == 1,
    "tool_result_not_used": lambda s: any('"refund_eligible": true' in r.lower()
        for r in tool_results(s, "get_order")) and not hits_tool_result_not_used(s),
}

all_hits = collections.defaultdict(list)
for s in samples:
    for mode, fn in FILTERS.items():
        why = fn(s)
        if why: all_hits[mode].append((s, why))

print("=== depth search hits over all 250 sessions ===")
for mode in FILTERS:
    hs = all_hits[mode]
    new = [x for x in hs if x[0]["session_id"] not in reviewed]
    print(f"  {mode:34s} {len(hs):3d} hits  ({len(new)} not yet reviewed)")

# ---- batch 3: 25 unreviewed, spread across modes + close negatives ----
manifest = json.loads((STATE/"sample_manifest.json").read_text())
entries = {e["session_id"]: e for e in manifest["entries"]}
taken = set(entries)
picked = []

def take(sess, method, reason):
    if sess in taken or sess in reviewed: return False
    entries[sess] = {"session_id": sess, "scenario_id": by_id[sess]["scenario_id"],
                     "batch": 3, "method": method, "reason": reason}
    taken.add(sess); picked.append(sess); return True

order = sorted(FILTERS, key=lambda m: len([x for x in all_hits[m] if x[0]["session_id"] not in taken]))
while len(picked) < 18:
    progressed = False
    for mode in order:
        if len(picked) >= 18: break
        for s, why in all_hits[mode]:
            if take(s["session_id"], f"depth_search_{mode}", why):
                progressed = True; break
    if not progressed: break

for mode, pred in NEGATIVES.items():
    cands = [s for s in samples if s["session_id"] not in taken
             and s["session_id"] not in reviewed and pred(s)]
    rnd.shuffle(cands)
    for s in cands[:2]:
        take(s["session_id"], f"close_negative_{mode}",
             f"superficially similar to {mode} but the signal is absent; tests the boundary")

pool = [s for s in samples if s["session_id"] not in taken and s["session_id"] not in reviewed]
rnd.shuffle(pool)
for s in pool:
    if len(picked) >= 25: break
    take(s["session_id"], "depth_search_filler",
         "retrieved to complete batch 3 after the mode-specific searches")

manifest["entries"] = [entries[k] for k in sorted(entries, key=lambda k: by_id[k]["scenario_id"])]
(STATE/"sample_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
for s in samples:
    s["batch"] = entries.get(s["session_id"], {}).get("batch")
(STATE/"samples.json").write_text(json.dumps({"samples": samples}, indent=2) + "\n")

# ---- suggestions: every hit, including rechecks of already-reviewed sessions ----
sug = []
n = 0
for mode, hs in all_hits.items():
    for s, why in hs:
        n += 1
        sug.append({"id": f"s{n:04d}", "trace_id": s["session_id"], "scenario_id": s["scenario_id"],
                    "mode": mode, "note": f"[{mode}] {why}", "signal": "deterministic_filter",
                    "already_reviewed": s["session_id"] in reviewed,
                    "batch": entries.get(s["session_id"], {}).get("batch")})
(STATE/"suggestions.json").write_text(json.dumps(sug, indent=2) + "\n")

print(f"\nbatch 3 selected: {len(picked)}")
print("methods:", dict(collections.Counter(entries[p]['method'] for p in picked)))
print("manifest total:", len(entries), dict(sorted(collections.Counter(
    e['batch'] for e in entries.values()).items())))
print(f"suggestions written: {len(sug)} "
      f"({sum(1 for x in sug if x['already_reviewed'])} on already-reviewed sessions)")
