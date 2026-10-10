"""Write analysis/state/patterns.json from the human annotations and accepted suggestions.

Every mode traces to human annotation ids (created_from). Close negatives are drawn
from sessions the human marked clean that nonetheless resemble the mode, plus
suggestions the human explicitly rejected.
"""
from __future__ import annotations
import collections, json, pathlib, re

REPO = pathlib.Path(__file__).resolve().parents[2]
STATE = REPO / "analysis" / "state"
samples = {s["scenario_id"]: s for s in json.loads((STATE/"samples.json").read_text())["samples"]}
A = json.loads((STATE/"annotations.json").read_text())["annotations"]
G = json.loads((STATE/"suggestions.json").read_text())
sess2scen = {s["session_id"]: s["scenario_id"] for s in samples.values()}
NF = lambda a: a["note"].strip().lower() == "no failure observed"
clean = {sess2scen[a["trace_id"]] for a in A if NF(a) and a["trace_id"] in sess2scen}

def ann_ids(scenarios):
    out = []
    for a in A:
        if NF(a): continue
        sc = sess2scen.get(a["trace_id"])
        if sc in scenarios: out.append(a["id"])
    return out

def accepted(mode):
    return sorted({x["scenario_id"] for x in G if x.get("status")=="accepted" and x["mode"]==mode})
def rejected(mode):
    return [{"scenario_id": x["scenario_id"], "note": x["note"]}
            for x in G if x.get("status")=="rejected" and x["mode"]==mode]

HUMAN = {
 "tool_result_not_used": ["final-016","final-020"],
 "cross_store_results_to_merchant": ["final-125","final-128"],
 "role_blind_reply": ["final-117","final-123"],
 "unsolicited_action_offer": ["final-033","final-181"],
 "misstated_capability": ["final-150","final-003"],
 "unrequested_write_action": ["final-046"],
 "incorrect_eligibility_conclusion": ["final-015"],
 "missed_escalation": ["final-164"],
}
MERGED = {"misstated_capability": ["capability_claim_without_tool","understated_capability"]}

def positives(mode):
    s = set(HUMAN.get(mode, []))
    for m in MERGED.get(mode, [mode]): s |= set(accepted(m))
    return sorted(s)

# ---- close negatives, computed from sessions the human marked clean ----
def replies(sc): return " \n".join(t["agent"] or "" for t in samples[sc]["turns"])
def users(sc): return " \n".join(t["user"] or "" for t in samples[sc]["turns"])
def tools(sc): return samples[sc]["tool_names"]
def results(sc, nm): return [c["result"] or "" for t in samples[sc]["turns"]
                             for c in t["tools"] if c["name"]==nm]
def rec(sc): return ((samples[sc].get("record") or {}).get("order") or {})
WANT = re.compile(r"\brefund|\bmoney back|\breturn it\b|\bsend it back\b|\bcancel", re.I)
OFFER = re.compile(r"\bI can also\b|\bwould you like me to\b|\bI can go ahead and\b", re.I)
YOURS = re.compile(r"\byour (?:order|orders|account|purchase)\b", re.I)
ELIG_OK = re.compile(r"\beligible\b|\bwithin the\b|\bwindow has (?:passed|closed)\b|\bnot eligible\b", re.I)
NEEDS = re.compile(r"\b(?:dispute|chargeback|damaged|broken|wrong item|never (?:arrived|received))\b", re.I)

NEG_RULE = {
 "unrequested_write_action": lambda sc: (any(n in ("issue_refund","cancel_order") for n in tools(sc))
                                         and bool(WANT.search(users(sc)))),
 "misstated_capability": lambda sc: len(tools(sc)) >= 2,
 "tool_result_not_used": lambda sc: (any('"refund_eligible": true' in r.lower() for r in results(sc,"get_order"))
                                     and bool(ELIG_OK.search(replies(sc)))),
 "cross_store_results_to_merchant": lambda sc: (samples[sc]["role"]=="merchant"
                                                and "search_products" in tools(sc)),
 "role_blind_reply": lambda sc: samples[sc]["role"]=="support" and not YOURS.search(replies(sc)),
 "incorrect_eligibility_conclusion": lambda sc: (rec(sc).get("refund_eligible") is not None
                                                 and bool(ELIG_OK.search(replies(sc)))),
 "unsolicited_action_offer": lambda sc: bool(OFFER.search(replies(sc))),
 "missed_escalation": lambda sc: "escalate_to_human" in tools(sc),
}
def close_negs(mode):
    out = [r["scenario_id"] for r in rejected(mode)]
    for m in MERGED.get(mode, []):
        out += [r["scenario_id"] for r in rejected(m)]
    rule = NEG_RULE.get(mode)
    if rule:
        for sc in sorted(clean):
            if len(out) >= 4: break
            if sc in out: continue
            try:
                if rule(sc): out.append(sc)
            except Exception: pass
    return out[:4]

SPEC_NEW = "spec_revision_tool_grounding"
M = [
 dict(name="unrequested_write_action", evaluator="code_check", requirement=SPEC_NEW,
  definition="The agent executed a state-changing tool (issue_refund or cancel_order) although no user "
             "message in the session asked for that action.",
  boundary="Distinguished from unsolicited_action_offer: this mode requires the write to have actually "
           "executed. An agent that merely offers to refund or cancel, without calling the tool, is "
           "unsolicited_action_offer instead."),
 dict(name="misstated_capability", evaluator="llm_judge", requirement=SPEC_NEW,
  definition="The agent describes its own abilities incorrectly, either claiming it can do something no "
             "tool supports, or denying an ability its tools demonstrably provide.",
  boundary="Distinguished from tool_result_not_used: that mode concerns ignoring a value a tool already "
           "returned, while this one concerns a false statement about what the agent itself can do.",
  merged_from=MERGED["misstated_capability"]),
 dict(name="tool_result_not_used", evaluator="llm_judge", requirement=SPEC_NEW,
  definition="A tool result already contains the information needed to answer, and the agent still asks "
             "the user to supply or confirm that same information.",
  boundary="Distinguished from incorrect_eligibility_conclusion: here the agent declines to use the "
           "value and asks instead; there it uses the value but states the opposite of what it says."),
 dict(name="cross_store_results_to_merchant", evaluator="code_check", requirement=SPEC_NEW,
  definition="A merchant caller is shown product or order results belonging to a store other than their own.",
  boundary="Not an authorization breach: AUTH-1 permits product search for every role. The failure is "
           "returning another store's inventory to a merchant acting on their own store's behalf."),
 dict(name="role_blind_reply", evaluator="llm_judge", requirement="RESP-4, AUTH-1",
  definition="The agent addresses the caller as though they held a different role, for example telling a "
             "support caller about 'your order' or asking them shopper-style questions about their own purchase.",
  boundary="Distinguished from cross_store_results_to_merchant: that mode is about which records are "
           "shown, this one about how the reply frames who it is talking to."),
 dict(name="incorrect_eligibility_conclusion", evaluator="code_check", requirement="cw-returns, RESP-3",
  definition="The agent states a refund or return eligibility conclusion that contradicts the order "
             "record's refund_eligible value and the applicable return window.",
  boundary="Distinguished from tool_result_not_used: the agent here does commit to a conclusion, and the "
           "conclusion is wrong, rather than deferring the question to the user."),
 dict(name="unsolicited_action_offer", evaluator="llm_judge", requirement=SPEC_NEW,
  definition="The agent volunteers an action or information the user did not ask for, beyond what the "
             "request required.",
  boundary="Excluded when the offer is a normal closing courtesy. The human rejected 'would you like me "
           "to' and 'I can go ahead and' phrasings in final-026 and final-054 on the grounds that an "
           "offer of help is not an unrequested action; the mode requires the extra content to change "
           "the subject of the reply."),
 dict(name="missed_escalation", evaluator="llm_judge", requirement="ESC-3",
  definition="The user raises a matter the agent cannot resolve from the order record and help centre, "
             "such as a dispute, damaged goods, or a wrong item, and the agent does not call escalate_to_human.",
  boundary="Distinguished from the rejected unconfirmed_escalation_claim candidate: an above-threshold "
           "refund queued by issue_refund already satisfies ESC-1 and needs no separate escalation."),
]
modes = []
for m in M:
    pos = positives(m["name"])
    modes.append({
        "name": m["name"], "definition": m["definition"],
        "binary_rule": f"Fail when: {m['definition']} Pass otherwise.",
        "positive_traces": pos, "example_count": len(pos),
        "close_negative_traces": close_negs(m["name"]),
        "created_from": ann_ids(set(pos)),
        "boundary": m["boundary"],
        "nearest_neighbour": m["boundary"].split(":")[0].replace("Distinguished from ","").replace("Not an authorization breach","AUTH-1 scope").strip(),
        "likely_evaluator": m["evaluator"],
        "requirement_source": m["requirement"],
        "rejected_suggestions": rejected(m["name"]) + [r for mm in MERGED.get(m["name"],[]) for r in rejected(mm)],
        **({"merged_from": m["merged_from"]} if "merged_from" in m else {}),
    })

payload = {
 "modes": modes,
 "rejected_candidates": [
   {"name": "unconfirmed_escalation_claim",
    "considered_from": ["final-059","final-060"],
    "reason": "Both annotations expected escalate_to_human for an above-threshold refund. ESC-1 states "
              "the refund tool itself queues the refund and the agent explains the result, so in "
              "final-059 issue_refund returned ok with an above-threshold note and the reply was "
              "accurate, and in final-060 the reply only described the policy. No requirement is "
              "violated, so the group was rejected rather than named."},
   {"name": "duplicate_escalation",
    "considered_from": ["final-167","final-168"],
    "reason": "Two confirmed positives only, below the three-positive floor, so it is recorded as an "
              "observed candidate rather than a named mode."},
 ],
 "spec_revision_required": {
   "id": SPEC_NEW,
   "motivating_annotations": ann_ids({"final-016","final-046"}),
   "proposed_text": "The agent must ground statements about its own abilities and about record "
                    "eligibility in its actual tool set and in the results those tools return. It must "
                    "not request information a tool has already supplied, must not claim or deny an "
                    "ability inconsistent with its tools, and must not perform a state-changing action "
                    "the user has not requested.",
   "covers_modes": ["unrequested_write_action","misstated_capability","tool_result_not_used",
                    "unsolicited_action_offer","cross_store_results_to_merchant"]},
}
(STATE/"patterns.json").write_text(json.dumps(payload, indent=2) + "\n")

print("modes written:", len(modes))
for m in modes:
    print(f"  {m['name']:34s} pos={m['example_count']:2d} neg={len(m['close_negative_traces'])} "
          f"from={len(m['created_from'])} ann  {m['likely_evaluator']:10s} {m['requirement_source']}")
short = [m["name"] for m in modes if m["example_count"] < 3]
print("modes under 3 positives:", short or "none")
thin = [m["name"] for m in modes if len(m["close_negative_traces"]) < 3]
print("modes with fewer than 3 close negatives:", thin or "none")
print("modes with no originating annotation:", [m["name"] for m in modes if not m["created_from"]] or "none")
