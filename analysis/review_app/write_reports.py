"""Generate analysis/report/review_summary.md and interface_comparison.md from saved state."""
from __future__ import annotations
import collections, json, pathlib

REPO = pathlib.Path(__file__).resolve().parents[2]
STATE = REPO/"analysis"/"state"; REP = REPO/"analysis"/"report"; REP.mkdir(parents=True, exist_ok=True)
S = json.loads((STATE/"samples.json").read_text())["samples"]
by_sess = {s["session_id"]: s for s in S}
A = json.loads((STATE/"annotations.json").read_text())["annotations"]
G = json.loads((STATE/"suggestions.json").read_text())
P = json.loads((STATE/"patterns.json").read_text())
MAN = json.loads((STATE/"sample_manifest.json").read_text())
LS = json.loads((STATE/"labels_summary.json").read_text())

NF = lambda a: a["note"].strip().lower() == "no failure observed"
rev = {a["trace_id"] for a in A}
batches = collections.Counter(e["batch"] for e in MAN["entries"])
methods = collections.Counter(e["method"] for e in MAN["entries"])
roles = collections.Counter(by_sess[s]["role"] for s in rev if s in by_sess)
groups = collections.Counter(by_sess[s]["scenario_group"] for s in rev if s in by_sess)
intents = collections.Counter(by_sess[s]["intent"] for s in rev if s in by_sess)
sug_status = collections.Counter(x.get("status") or "pending" for x in G)

L = ["# Review summary", "",
 f"Reviewed **{len(rev)}** distinct sessions of the 250 in the Homework 3 trace store "
 f"({len(json.loads((REPO/'traces/support_traces.json').read_text())['traces'])} Langfuse traces; "
 "Cartwheel writes one trace per user turn, so the review unit is the session).", "",
 "## Sample size and composition", "",
 "| batch | selection method | sessions |", "|---|---|---:|"]
BD = {1: "15 uniform random + 15 k-means cluster representatives",
      2: "30 stratified on user role, the dimension fixed before any outcome was inspected",
      3: "depth-search retrievals for candidate modes, plus deliberate close negatives",
      4: "uniform random, drawn last, as a saturation check"}
for b in sorted(batches):
    L.append(f"| {b} | {BD.get(b,'')} | {batches[b]} |")
L += ["", "Selection methods: " + ", ".join(f"`{k}` ({v})" for k, v in sorted(methods.items())), "",
 f"- roles: " + ", ".join(f"{k} {v}" for k, v in sorted(roles.items())),
 f"- groups: " + ", ".join(f"{k} {v}" for k, v in sorted(groups.items())),
 f"- intents: " + ", ".join(f"{k} {v}" for k, v in sorted(intents.items())),
 f"- annotations recorded: {len(A)}, of which {sum(1 for a in A if NF(a))} are "
 f'"no failure observed"', "",
 "Batches do not overlap and no session is counted toward more than one.", "",
 "## Saturation check on the final 15", "",
 "The batch 4 sessions produced **one** previously unseen consequential mode, `missed_escalation`, "
 "from the annotation on `final-164`. The other new note in that batch, on `final-181`, folded into "
 "the existing `unsolicited_action_offer` rather than forming a new mode. One new mode in fifteen "
 "uniformly drawn sessions was taken as reasonable stability, so no further batch was reviewed.", "",
 "## Failure modes and sample fractions", "",
 "Figures below are **sample fractions over this review set**, not prevalence estimates. Clustering, "
 "role stratification and depth searches deliberately changed the composition of the reviewed sample, "
 "so these fractions are biased upward relative to the full store. Homework 5 estimates prevalence "
 "over the complete Module 1 trace store.", "",
 "| mode | fail | pass | sample fraction | evaluator | requirement |", "|---|---:|---:|---:|---|---|"]
for m in P["modes"]:
    v = LS["modes"][m["name"]]
    L.append(f"| `{m['name']}` | {v['fail']} | {v['pass']} | {v['sample_fraction']:.3f} | "
             f"{m['likely_evaluator']} | {m['requirement_source']} |")
L += ["", f"Every reviewed session carries one judgment per mode "
 f"({LS['reviewed_sessions']} x {len(P['modes'])} = {LS['reviewed_sessions']*len(P['modes'])} judgments). "
 "A Fail is a confirmed positive, from a human annotation or a suggestion the human accepted. A Pass "
 "records that the session was reviewed and the mode was not observed in it.", "",
 f"{sug_status.get('pending',0)} retrieval suggestions remain undecided, "
 f"{sug_status.get('accepted',0)} were accepted and {sug_status.get('rejected',0)} rejected. The "
 "undecided ones may understate the modes they belong to, most of them "
 "`unsolicited_action_offer`, which had already reached its three confirmed positives.", "",
 "## The taxonomy revision", "",
 "`capability_claim_without_tool` and `understated_capability` began as two candidate modes. The first "
 "covered replies offering an ability no tool supports, such as `final-150` offering to check the status "
 "of an existing ticket when no tool exposes ticket status. The second covered replies denying an "
 "ability the tools do provide, such as `final-003` claiming it could not see store-specific overrides. "
 "They were merged into `misstated_capability` because one product change fixes both: constrain the "
 "agent's statements about itself to its actual nine tools. The merge test used throughout was whether "
 "fixing one behaviour would fix the other.", "",
 "## A rejected group", "",
 P["rejected_candidates"][0]["reason"], "",
 "## A rejected search suggestion and the boundary that excludes it", ""]
rej = [x for x in G if x.get("status") == "rejected"]
for x in rej:
    L.append(f"- `{x['scenario_id']}` for `{x['mode']}`: {x['note']}")
L += ["", "The `unsolicited_action_offer` rejections set the boundary: a closing offer of further help "
 "is not an unrequested action. The mode requires the additional content to change the subject of the "
 "reply, as in `final-033`, where a shipping-status question was answered with an offer to cancel the "
 "order. The `tool_result_not_used` rejection on `final-049` sets a second boundary: a confirming "
 "question is only a failure when the tool result already settles the question being asked.", "",
 "## Relationship to SPEC.md", "",
 f"Three modes map to existing requirements: `role_blind_reply` to RESP-4 and AUTH-1, "
 "`incorrect_eligibility_conclusion` to `cw-returns` and RESP-3, and `missed_escalation` to ESC-3.", "",
 "The remaining five described behaviour the specification neither required nor forbade, so a revision "
 "was recorded before any label was assigned, as "
 f"`{P['spec_revision_required']['id']}`:", "",
 "> " + P["spec_revision_required"]["proposed_text"], "",
 "The motivating annotations are on `final-016`, where `get_order` returned `refund_eligible` true and "
 "the reply asked the shopper for today's date, and `final-046`, where a refund executed although no "
 "user message requested one.", ""]
(REP/"review_summary.md").write_text("\n".join(L))

C = ["# Interface comparison", "",
 "The review interface lives in `analysis/review_app/` and reuses the reference server's endpoint "
 "contract so the state files stay readable by `analysis/helpers` and the Module 3 tooling.", "",
 "## One design retained from the reference interface", "",
 "The four-view structure and the file-backed API were kept unchanged: a trace view for reading and "
 "annotating, a map view projecting every session into two dimensions coloured by cluster, a progress "
 "view, and a structured labelling view that only opens once the taxonomy has stabilised. The inline "
 "annotation pattern was also retained, including wrapping the selected range in a temporary highlight "
 "before focusing the input, because the browser clears the native selection when focus moves.", "",
 "## One design changed after inspecting the traces", "",
 "A pinned answer-key panel was added beside the conversation. Every Cartwheel scenario carries a "
 "verified expected outcome, the database record it was derived from, the applicable policy text and "
 "the relevant `SPEC.md` requirements. Reviewing without them meant leaving the trace to look up "
 "whether a reply was actually wrong, which is the slowest step in open coding. The panel shows the "
 "expected outcome and its reason and source, the order or product record with its status, dates, "
 "window and eligibility, the caller's role and store, the full text of each applicable policy, the "
 "text of each cited requirement, and the seeded world date of 2026-07-01 that all date arithmetic "
 "depends on.", "",
 "A second, smaller adaptation follows from the trace structure: Cartwheel writes one Langfuse trace "
 "per user turn, so 250 scenarios produced 359 traces and 100 sessions span two or three of them. The "
 "interface groups by `cartwheel.session_id` and renders the whole conversation in order with turn "
 "dividers, because a follow-up turn read in isolation hides the tool calls from earlier turns.", "",
 "## One remaining limitation", "",
 "Structured labels are written to `analysis/state/labels/` through the interface and a helper script, "
 "but the interface does not push Langfuse scores itself; that is a separate step. Margin notes are "
 "also positioned from the highlighted span's bounding box, so a note whose quoted text appears more "
 "than once in a session attaches to the first occurrence. Finally, the map view draws no cluster "
 "hulls, so cluster membership is readable only from node colour.", ""]
(REP/"interface_comparison.md").write_text("\n".join(C))

print("wrote", REP/"review_summary.md", "and", REP/"interface_comparison.md")
print("review_summary words:", len((REP/'review_summary.md').read_text().split()))
print("interface_comparison words:", len((REP/'interface_comparison.md').read_text().split()))
