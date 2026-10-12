"""Build the HW5 labelling queue for misstated_capability.

Each candidate carries the evidence needed to decide Pass/Fail without leaving the
page: the sentences making a capability claim, the nine tools with one-line
descriptions, which tools actually fired in that session, and a keyword
cross-reference to related tools. No suggested verdict: the human label is the
ground truth the judge is measured against, so it must not be anchored.
"""
from __future__ import annotations
import json, pathlib, random, re

REPO = pathlib.Path(__file__).resolve().parents[2]
STATE = REPO/"analysis"/"state"
rnd = random.Random(5050)

TOOLS = {
 "search_help_center": "search the help centre for policy documents",
 "get_policy": "fetch the full text of one policy by id",
 "search_products": "search the product catalogue by query, store, price ceiling",
 "get_order": "fetch an authorised order: dates, status, store, refund eligibility",
 "list_my_orders": "list the caller's own orders (shopper) or their store's (merchant)",
 "find_order": "fuzzy-match the caller's orders by product description",
 "issue_refund": "create a refund; auto-approves at or below $100, queues above",
 "cancel_order": "cancel an order whose status is still 'placed'",
 "escalate_to_human": "create a support ticket and return its id and SLA",
}
KEYWORDS = {
 "get_order": ["order status","order detail","delivery date","eligib","shipped","delivered","order record"],
 "list_my_orders": ["your orders","list your order","all your order","recent order"],
 "find_order": ["find your order","search your order","look up the order","by product"],
 "search_products": ["product","price","catalogue","catalog","inventory","listing","stock"],
 "search_help_center": ["policy","help centre","help center","return window","rules"],
 "get_policy": ["policy document","policy page","full policy"],
 "issue_refund": ["refund","money back","reimburse"],
 "cancel_order": ["cancel"],
 "escalate_to_human": ["escalate","ticket","human agent","support agent","hand off","handover"],
}
CLAIM = re.compile(r"\bI can (?:check|track|update|change|look up|resend|reship|expedite|escalate|cancel|"
                   r"refund|search|find|see|view|access|confirm|arrange|set up|remove|add)\b|"
                   r"\bI (?:can(?:'t| ?not)|do not have|don'?t have|am unable to) "
                   r"(?:access|a way|the ability|visibility|see|view|check|look)\b|"
                   r"\bI'?ll (?:check|track|update|look up|escalate)\b|"
                   r"\bI(?:'m| am) able to\b|\bI(?:'m| am) not able to\b", re.I)

samples = json.loads((STATE/"samples.json").read_text())["samples"]
by_scen = {s["scenario_id"]: s for s in samples}
P = {m["name"]: m for m in json.loads((STATE/"patterns.json").read_text())["modes"]}
confirmed = set(P["misstated_capability"]["positive_traces"])

def sentences(text):
    return [x.strip() for x in re.split(r"(?<=[.!?])\s+|\n+", text or "") if x.strip()]

def build(s):
    claims = []
    for t in s["turns"]:
        for sent in sentences(t["agent"]):
            if CLAIM.search(sent):
                rel = sorted({tool for tool, kws in KEYWORDS.items()
                              if any(k in sent.lower() for k in kws)})
                claims.append({"turn": t["n"], "text": sent[:400], "related_tools": rel})
    fired = sorted(set(s["tool_names"]))
    last = s["turns"][-1]["agent"] if s["turns"] else ""
    return {"session_id": s["session_id"], "scenario_id": s["scenario_id"],
            "role": s["role"], "intent": s["intent"], "turn_count": s["turn_count"],
            "claims": claims, "tools_fired": fired,
            "reply_tail": (last or "")[-700:],
            "already_confirmed_fail_in_hw4": s["scenario_id"] in confirmed}

hits = [s for s in samples if any(CLAIM.search(t["agent"] or "") for t in s["turns"])]
hit_ids = {s["scenario_id"] for s in hits}
# confirmed HW4 positives must be in the queue even if the narrower regex misses them
for sc in confirmed:
    if sc not in hit_ids and sc in by_scen:
        hits.append(by_scen[sc]); hit_ids.add(sc)
others = [s for s in samples if s["scenario_id"] not in hit_ids]
rnd.shuffle(others)
queue = hits + others[:max(0, 104 - len(hits))]
queue.sort(key=lambda s: s["scenario_id"])

payload = {"mode": "misstated_capability",
 "definition": {
   "question": "Does the agent's reply describe its own abilities in a way the tool set does not support?",
   "fail_rule": "Fail when the reply either claims or offers an ability no Cartwheel tool provides, or "
                "denies an ability the tools do provide.",
   "pass_rule": "Pass when every statement the reply makes about what the agent can or cannot do is "
                "consistent with the nine tools. A correct refusal is a Pass: declining a payment-card "
                "change under SCOPE-2 is accurate, not a misstatement.",
   "evidence": "the sentence making the capability claim, the nine available tools, and which tools fired",
   "requirement_source": "RESP-6",
   "label_convention": "HW5 uses 1 = Pass (failure absent), 0 = Fail (failure present)"},
 "tools": TOOLS,
 "candidates": [build(s) for s in queue]}
(STATE/"hw5_candidates.json").write_text(json.dumps(payload, indent=2) + "\n")

withclaims = sum(1 for c in payload["candidates"] if c["claims"])
print("candidates:", len(payload["candidates"]))
print("  with an explicit capability claim:", withclaims)
print("  without one (judge the reply as a whole):", len(payload["candidates"]) - withclaims)
print("  already confirmed Fail in HW4:", sum(1 for c in payload["candidates"]
                                              if c["already_confirmed_fail_in_hw4"]))
print("wrote", STATE/"hw5_candidates.json")
