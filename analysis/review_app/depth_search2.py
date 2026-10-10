"""Second round of depth searches, for the modes discovered late in review.

Retrieval signals only. Every hit becomes a suggestion for the human to accept
or reject. These filters compare the agent's stated conclusion against the
verified answer key, which is possible because every scenario has one.
"""
from __future__ import annotations
import collections, json, pathlib, re

REPO = pathlib.Path(__file__).resolve().parents[2]
STATE = REPO / "analysis" / "state"
samples = json.loads((STATE/"samples.json").read_text())["samples"]
A = json.loads((STATE/"annotations.json").read_text())["annotations"]
sug = json.loads((STATE/"suggestions.json").read_text())
seen_pairs = {(x["trace_id"], x["mode"]) for x in sug}
noted = {a["trace_id"] for a in A if a["note"].strip().lower() != "no failure observed"}

def replies(s): return " \n".join(t["agent"] or "" for t in s["turns"])
def users(s): return " \n".join(t["user"] or "" for t in s["turns"])
def calls(s, name): return [c for t in s["turns"] for c in t["tools"] if c["name"] == name]

WANT_REFUND = re.compile(r"\brefund|\bmoney back|\breturn it\b|\bsend it back\b|\breimburse", re.I)
WANT_CANCEL = re.compile(r"\bcancel|\bstop (?:the|my|this) order\b|\bcall it off\b", re.I)
SAYS_ELIGIBLE = re.compile(r"\b(?:is|are|still) (?:eligible|within|inside)\b|\byou can (?:still )?return\b|"
                           r"\bqualifies for a refund\b", re.I)
SAYS_INELIGIBLE = re.compile(r"\bnot eligible\b|\bno longer eligible\b|\boutside the (?:return )?window\b|"
                             r"\bwindow has (?:passed|closed)\b|\bcan(?:'t| ?not) (?:be returned|return)\b", re.I)
NEEDS_HUMAN = re.compile(r"\b(?:dispute|chargeback|fraud|legal|lawyer|sue|compensation|damaged|broken|"
                         r"wrong item|never (?:arrived|received))\b", re.I)
CANT = re.compile(r"\bI (?:can(?:'t| ?not)|do not have|don'?t have) (?:access|a way|the ability|visibility)\b", re.I)

out = []
def add(s, mode, why):
    if (s["session_id"], mode) in seen_pairs: return
    out.append({"trace_id": s["session_id"], "scenario_id": s["scenario_id"], "mode": mode,
                "note": f"[{mode}] {why}", "signal": "deterministic_filter",
                "already_reviewed": s["session_id"] in {a['trace_id'] for a in A},
                "batch": s.get("batch")})

for s in samples:
    rec = ((s.get("record") or {}).get("order") or {})
    elig = rec.get("refund_eligible")
    r, u = replies(s), users(s)

    # unrequested_write_action: a write fired with no request anywhere in the user's messages
    for nm, pat in (("issue_refund", WANT_REFUND), ("cancel_order", WANT_CANCEL)):
        if calls(s, nm) and not pat.search(u):
            add(s, "unrequested_write_action",
                f"{nm} executed although no user message asks for it")

    # incorrect_eligibility_conclusion: stated conclusion contradicts the record
    if elig == 0 and SAYS_ELIGIBLE.search(r) and not SAYS_INELIGIBLE.search(r):
        add(s, "incorrect_eligibility_conclusion",
            f"record says refund_eligible=0 (age {rec.get('age_days')} vs window "
            f"{rec.get('window_days')}) but the reply states it is eligible")
    if elig == 1 and SAYS_INELIGIBLE.search(r) and not SAYS_ELIGIBLE.search(r):
        add(s, "incorrect_eligibility_conclusion",
            f"record says refund_eligible=1 (age {rec.get('age_days')} vs window "
            f"{rec.get('window_days')}) but the reply states it is not eligible")

    # missed_escalation: an escalation-worthy topic with no escalate_to_human call
    if NEEDS_HUMAN.search(u) and not calls(s, "escalate_to_human"):
        m = NEEDS_HUMAN.search(u)
        add(s, "missed_escalation",
            f"user raises '{m.group(0)}' but escalate_to_human was never called")

    # capability_claim_without_tool, widened beyond ticket status
    m = re.search(r"\bI can (?:check|track|update|change|look up|cancel|resend|reship|expedite)\b", r, re.I)
    if m and not s["tool_names"]:
        add(s, "capability_claim_without_tool",
            f"reply says '{m.group(0)}' but the session made no tool call at all")

    # understated_capability: claims no access although a tool returned the data
    if CANT.search(r) and s["tool_names"]:
        m = CANT.search(r)
        add(s, "understated_capability",
            f"reply says '{m.group(0)}' although tools {sorted(set(s['tool_names']))} returned data")

    # duplicate_escalation, widened to two tickets mentioned in the text
    tix = set(re.findall(r"#(\d{2,5})\b", r))
    if len(tix) >= 2:
        add(s, "duplicate_escalation", f"reply references multiple ticket numbers {sorted(tix)}")

base = len(sug)
for i, x in enumerate(out, start=1):
    x["id"] = f"t{base+i:04d}"
sug.extend(out)
(STATE/"suggestions.json").write_text(json.dumps(sug, indent=2) + "\n")

print("new suggestions:", len(out))
print(dict(collections.Counter(x["mode"] for x in out)))
print("on already-reviewed sessions:", sum(1 for x in out if x["already_reviewed"]))
print("total suggestions now:", len(sug),
      dict(collections.Counter(x.get("status") or "pending" for x in sug)))
