"""Build the labelling queue for missing_policy_citation (RESP-1).

Groups each session by a deterministic signal:
  A  no policy-derived claim detected      -> suggested Pass
  B  policy claim present, identifier cited -> suggested Pass
  C  policy claim present, no identifier    -> suggested Fail  (the real decisions)

The suggestion is a mechanical signal, not a verdict: whether a cw-* or
store-*-policy identifier appears is a fact, but whether a sentence is genuinely
policy-derived is the human's call. Overrides are recorded.
"""
from __future__ import annotations
import collections, json, pathlib, random, re

REPO = pathlib.Path(__file__).resolve().parents[2]
STATE = REPO/"analysis"/"state"
rnd = random.Random(31337)

CITE = re.compile(r"\b(?:cw-[a-z-]+|store-[a-z-]+-policy)\b", re.I)
FACTS = [
 ("return window",    r"\b(?:7|14|21|30|45)\s*days?\b|\breturn window\b|\bwithin \d+ days?\b"),
 ("refund processing",r"\b5 to 10 business days\b|\boriginal payment method\b|\b5-10 business days\b"),
 ("approval threshold",r"\$100\b|\b100 dollars\b|auto-?approv|\bthreshold\b|queued for (?:human )?review"),
 ("restocking fee",   r"\b15\s*(?:percent|%)\b|\brestocking fee\b|\bopened items?\b"),
 ("cancellation rule",r"before (?:it |the order )?ships?\b|\bbefore shipment\b|\bonce .{0,15}ships?\b"),
 ("dispute window",   r"\b60 days?\b|\bdispute\b.{0,30}\bdays?\b"),
 ("payout schedule",  r"\bweekly\b.{0,20}\bpayout|\bpayout\b.{0,20}\bfriday|\bbusiness days?\b.{0,20}payout"),
 ("shipping limits",  r"\bhandling\b.{0,20}\bdays?\b|\btransit\b.{0,20}\bdays?\b"),
 ("escalation sla",   r"\b24 hours?\b|\bsla\b"),
]

def sentences(text):
    return [x.strip() for x in re.split(r"(?<=[.!?])\s+|\n+", text or "") if x.strip()]

samples = json.loads((STATE/"samples.json").read_text())["samples"]

def build(s):
    claims = []
    for t in s["turns"]:
        for sent in sentences(t["agent"]):
            kinds = sorted({k for k, rx in FACTS if re.search(rx, sent, re.I)})
            if kinds:
                claims.append({"turn": t["n"], "text": sent[:400], "kinds": kinds,
                               "cited_here": sorted(set(CITE.findall(sent)))})
    all_text = " \n".join(t["agent"] or "" for t in s["turns"])
    cites = sorted(set(CITE.findall(all_text)))
    if not claims:
        grp, sug, why = "A", 1, "no policy-derived claim detected in the reply"
    elif cites:
        grp, sug, why = "B", 1, f"policy claim present and identifier(s) cited: {', '.join(cites)}"
    else:
        grp, sug, why = "C", 0, "policy claim present but no policy identifier anywhere in the reply"
    return {"session_id": s["session_id"], "scenario_id": s["scenario_id"],
            "role": s["role"], "intent": s["intent"], "turn_count": s["turn_count"],
            "group": grp, "suggested": sug, "signal": why,
            "claims": claims[:4], "citations_found": cites,
            "applicable_policy": s.get("applicable_policy"),
            "reply_tail": ((s["turns"][-1]["agent"] if s["turns"] else "") or "")[-700:]}

allc = [build(s) for s in samples]
byg = collections.defaultdict(list)
for c in allc: byg[c["group"]].append(c)
for g in byg: rnd.shuffle(byg[g])

queue = byg["C"] + byg["B"][:32] + byg["A"][:22]
queue.sort(key=lambda c: (c["group"], c["scenario_id"]))

payload = {"mode": "missing_policy_citation",
 "definition": {
   "question": "Does the reply state a fact derived from a policy document without citing the policy identifier?",
   "fail_rule": "Fail when the reply asserts a policy-derived fact - a return-window length, the "
                "auto-approval threshold, refund processing time, the restocking-fee rule, the "
                "cancellation cutoff, the dispute window, the payout schedule, shipping limits or the "
                "escalation SLA - and no policy identifier appears for it.",
   "pass_rule": "Pass when the reply makes no policy-derived claim, or cites the identifier for the "
                "claims it makes. A statement about this particular order (its status, its dates, its "
                "own total) is not a policy-derived claim.",
   "evidence": "the claim sentence, and whether a cw-* or store-*-policy identifier appears",
   "requirement_source": "RESP-1",
   "label_convention": "HW5 uses 1 = Pass (failure absent), 0 = Fail (failure present)"},
 "groups": {"A": "no policy claim detected (suggested Pass)",
            "B": "policy claim with an identifier cited (suggested Pass)",
            "C": "policy claim with no identifier (suggested Fail - these need your read)"},
 "candidates": queue}
(STATE/"hw5b_candidates.json").write_text(json.dumps(payload, indent=2) + "\n")

print("all sessions:", len(allc), dict(collections.Counter(c["group"] for c in allc)))
print("queued:", len(queue), dict(collections.Counter(c["group"] for c in queue)))
print("  suggested Fail (group C):", sum(1 for c in queue if c["suggested"] == 0))
print("  suggested Pass (A+B):   ", sum(1 for c in queue if c["suggested"] == 1))
print("claim kinds across group C:", dict(collections.Counter(
    k for c in byg["C"] for cl in c["claims"] for k in cl["kinds"])))
print("wrote", STATE/"hw5b_candidates.json")
