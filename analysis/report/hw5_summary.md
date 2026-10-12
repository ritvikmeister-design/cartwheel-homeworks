# Homework 5: an LLM judge for `missing_policy_citation`

## The mode

**Question.** Does the reply state a fact drawn from a Cartwheel policy document
without citing the policy identifier for it?

**Fail** when the reply asserts a policy-derived fact (a return-window length, refund
timing or destination, the $100 auto-approval threshold, the restocking-fee rule, the
cancellation cutoff, the dispute window, the payout schedule, shipping limits) and no
`cw-*` or `store-*-policy` identifier appears for it.

**Pass** when the reply asserts no policy-derived fact, or cites the identifier.

**Requirement source.** RESP-1, verbatim: *"Cite the policy identifier for every claim
derived from a policy document."* No specification revision was needed.

## A first attempt that failed, and why it is reported here

The mode first chosen was `misstated_capability`, carried over from Homework 4. It
reached an apparent 30 Fail labels, which met the handout's minimum. Inspecting the
training examples before writing the prompt showed two traces making the same claim
about ticket-status visibility with opposite labels, and four of six training Fails
were accurate statements about the agent's own limits.

The cause was a drift in the question being answered: on the probe batch, "Fail" had
been applied to mean *the agent did not do what the user asked* rather than *the agent
misdescribed its abilities*. For probes that request capabilities no tool provides, an
accurate refusal is a Pass under the stated definition.

Re-examining all 30 against the nine tools left **2** confirmed Fails out of 149
labelled conversations. `split_labels` then refused to split, which is the correct
behaviour: `check_split_class_counts` will not produce an evaluation split that cannot
support a rate. Those labels are retained at
`analysis/state/hw5_labels/misstated_capability.jsonl` with per-trace evidence.

The lesson carried into the second attempt was to choose a mode whose labels rest on a
quotable requirement rather than on judgment about intent.

## Base rates measured before committing to a mode

Signal counts over all 295 sessions, used to choose a labellable mode:

| candidate signal | hits | rate |
|---|---:|---:|
| unrequested extra content | 105 | 35.6% |
| missing policy citation | 59 | 20.0% |
| confirmation when the record settles it | 28 | 9.5% |
| empathy padding | 13 | 4.4% |
| reply over 900 characters | 10 | 3.4% |

`unrequested_extra_content` was the largest but was rejected: in Homework 4 two of
three such suggestions were rejected on the grounds that an offer of help is not an
unrequested action, so its boundary was known to be unstable.

Of the 59 missing-citation candidates, 43 were discarded on inspection because their
only policy-shaped figure was the 24-hour escalation SLA, which `escalate_to_human`
returns as `sla_hours` in its tool result and is therefore record-derived rather than
policy-derived. That left **16** confirmed Fails.

## Labels and splits

| | Pass | Fail | total |
|---|---:|---:|---:|
| labelled | 84 | 16 | 100 |
| train | 17 | 3 | 20 |
| dev | 34 | 6 | 40 |
| test | 33 | 7 | 40 |

`min_per_class` was lowered from 10 to **6** deliberately, because 16 Fail labels
cannot place 10 of that class in an eval split. The guard refused 10 and 8 first. The
consequence is wide intervals on the Fail-side rate, reported below rather than
smoothed over.

Of the 100 labels, 30 overrode the mechanical signal — all of them the tool-sourced
SLA cases.

## Judge

Model: **Llama 4 Maverick** (`llama4-maverick-17b-128e-instruct`), used for both
development and test. The handout specifies `gpt-4o-mini`; that model is not reachable
on this MetaGen entitlement (`400 Invalid model name`), and the agent under test runs
on Claude Sonnet 5, so Maverick also avoids a model grading its own output.

| version | TPR | TNR | agreement | disagreements |
|---|---|---|---|---:|
| v0 (dev) | 0.912 [0.770, 0.970] | 0.833 [0.437, 0.970] | 0.900 | 4 |
| v1 (dev) | 0.971 [0.851, 0.995] | 1.000 [0.610, 1.000] | 0.975 | 1 |
| **v1 (test, frozen)** | **0.970 [0.847, 0.995]** | **1.000 [0.646, 1.000]** | **0.975** | 1 |

Test confusion, Pass as the positive class: TP=32, FN=1, TN=7, FP=0.

### The one revision, and the disagreements that drove it

All four v0 disagreements were judge errors; no label changed. Three shared one cause:
the judge read *"since it hadn't shipped yet"* — this order's status, from `get_order` —
as asserting the cancellation-cutoff rule. The fourth let a refund id in the same
sentence excuse an uncited "5-10 business days".

v1 added two boundaries and two worked examples: a statement about what happened to
*this* order is record-derived even where a rule exists on the same subject, and one
sentence can carry both kinds of fact so each policy-derived fact is judged on whether
an identifier appears for it. It also told the judge to decide from what the reply
asserts rather than what it implies.

### Why revision stopped at v1

Dev holds 6 Fail labels. With TNR already 1.000 on those six, a second revision would
be tuning against a handful of examples, and the gain could not be distinguished from
noise. Test tracking dev almost exactly (0.970/1.000 against 0.971/1.000) supports
having stopped.

### A boundary the judge surfaced

The single remaining disagreement, `final-235`, is instructive. Turn 1 cited
`cw-restocking-fees` and `store-second-stitch-apparel-policy`; turn 2 then stated "over
the $100 auto-approval threshold… queued for a human agent" with no identifier. The
human label treated the reply as cited; the judge flagged the uncited second claim.

RESP-1 says *every* claim, so the judge is arguably the stricter and more faithful
reader, and the prompt's own "a partial citation is enough for PASS" rule is the lenient
party. The definition needs tightening to say whether citation is per claim or per
reply before this mode is used at scale.

## Would I use this judge?

As a **screening filter, yes.** It missed none of the 7 test Fails (FP=0, TNR 1.000) and
over-flagged one of 33 Passes, so running it over unlabelled traces would surface
candidates with few false alarms and no observed misses.

As a **measurement of how often this failure occurs, no.** The TNR interval runs from
0.646 to 1.000 on 7 Fail cases, so the detection rate is barely constrained. Any
prevalence figure derived from it would carry that uncertainty, and the corrected
estimate the helpers offer would have an interval too wide to act on. Thirty or more
Fail labels would be needed first, which on a 1.3% to 5% base rate means labelling
several hundred more traces or generating scenarios that target this mode directly.

## Deviations from the handout

1. `gpt-4o-mini` is unreachable on this entitlement; Maverick substituted for both dev
   and test.
2. The two external skills (`write-judge-prompt`, `validate-evaluator`) are installed
   from GitHub via `npx`, which this environment cannot reach. The equivalent local
   guidance in `analysis/skill/SKILL.md` phases 6 to 11 was followed instead.
3. `split_labels` in the installed helpers has no `eligible_trace_ids` parameter, unlike
   the handout's example. Eligibility was enforced by writing only labels that have a
   matching input record.
4. `split_labels` classifies `label == 1` as Fail, while the handout specifies 1 = Pass
   for HW5. The deliverable at `hw5_labels/<mode>.jsonl` uses the handout's convention;
   a helper-facing copy at `labels/<mode>_hw5.jsonl` uses the inverted one, under a
   distinct mode id so the Homework 4 label file is untouched. `judge_alignment`
   converts internally (`label = 1 - stored`), so Pass remains the positive class.
5. `load_store_traces` does not honour `CARTWHEEL_JUDGE_TRACE_SOURCE`; it reads Langfuse
   or the committed demo export. Our labels are keyed by `cartwheel.session_id` while
   that loader returns per-turn traces, so no session was findable. `run_judge`'s
   documented `classify` callable was used instead, reading
   `analysis/state/hw5b_trace_inputs.json`. `register_judge`, `run_judge`,
   `judge_alignment` and `freeze_judge` all still run, including the test-split guard.
6. Judge verdicts and critiques were inspected in the terminal rather than displayed in
   the Homework 4 review interface. Critiques are saved per judge version at
   `analysis/state/critiques-<judge_id>-<split>.json`.
