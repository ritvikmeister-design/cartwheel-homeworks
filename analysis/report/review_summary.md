# Review summary

Reviewed **110** distinct sessions of the 250 in the Homework 3 trace store (359 Langfuse traces; Cartwheel writes one trace per user turn, so the review unit is the session).

## Sample size and composition

| batch | selection method | sessions |
|---|---|---:|
| 1 | 15 uniform random + 15 k-means cluster representatives | 30 |
| 2 | 30 stratified on user role, the dimension fixed before any outcome was inspected | 30 |
| 3 | depth-search retrievals for candidate modes, plus deliberate close negatives | 26 |
| 4 | uniform random, drawn last, as a saturation check | 15 |

Selection methods: `close_negative_cross_store_results_to_merchant` (2), `close_negative_duplicate_escalation` (2), `close_negative_role_blind_reply` (2), `close_negative_tool_result_not_used` (2), `cluster_representative` (15), `depth_search_capability_claim_without_tool` (1), `depth_search_cross_store_results_to_merchant` (4), `depth_search_duplicate_escalation` (1), `depth_search_role_blind_reply` (2), `depth_search_tool_result_not_used` (5), `depth_search_unsolicited_action_offer` (5), `dimension_role` (30), `uniform_random` (15), `uniform_random_saturation_check` (15)

- roles: merchant 40, shopper 39, support 31
- groups: challenge 31, coverage 79
- intents: account_change 1, cancellation 11, dispute 6, order_status 16, out_of_scope 2, policy_question 17, product_search 20, refund 19, restocking_fee_question 2, return_deadline 16
- annotations recorded: 125, of which 71 are "no failure observed"

Batches do not overlap and no session is counted toward more than one.

## Saturation check on the final 15

The batch 4 sessions produced **one** previously unseen consequential mode, `missed_escalation`, from the annotation on `final-164`. The other new note in that batch, on `final-181`, folded into the existing `unsolicited_action_offer` rather than forming a new mode. One new mode in fifteen uniformly drawn sessions was taken as reasonable stability, so no further batch was reviewed.

## Failure modes and sample fractions

Figures below are **sample fractions over this review set**, not prevalence estimates. Clustering, role stratification and depth searches deliberately changed the composition of the reviewed sample, so these fractions are biased upward relative to the full store. Homework 5 estimates prevalence over the complete Module 1 trace store.

| mode | fail | pass | sample fraction | evaluator | requirement |
|---|---:|---:|---:|---|---|
| `unrequested_write_action` | 10 | 100 | 0.091 | code_check | spec_revision_tool_grounding |
| `misstated_capability` | 11 | 99 | 0.100 | llm_judge | spec_revision_tool_grounding |
| `tool_result_not_used` | 6 | 104 | 0.054 | llm_judge | spec_revision_tool_grounding |
| `cross_store_results_to_merchant` | 6 | 104 | 0.054 | code_check | spec_revision_tool_grounding |
| `role_blind_reply` | 4 | 106 | 0.036 | llm_judge | RESP-4, AUTH-1 |
| `incorrect_eligibility_conclusion` | 4 | 106 | 0.036 | code_check | cw-returns, RESP-3 |
| `unsolicited_action_offer` | 3 | 107 | 0.027 | llm_judge | spec_revision_tool_grounding |
| `missed_escalation` | 3 | 107 | 0.027 | llm_judge | ESC-3 |

Every reviewed session carries one judgment per mode (110 x 8 = 880 judgments). A Fail is a confirmed positive, from a human annotation or a suggestion the human accepted. A Pass records that the session was reviewed and the mode was not observed in it.

28 retrieval suggestions remain undecided, 36 were accepted and 3 rejected. The undecided ones may understate the modes they belong to, most of them `unsolicited_action_offer`, which had already reached its three confirmed positives.

## The taxonomy revision

`capability_claim_without_tool` and `understated_capability` began as two candidate modes. The first covered replies offering an ability no tool supports, such as `final-150` offering to check the status of an existing ticket when no tool exposes ticket status. The second covered replies denying an ability the tools do provide, such as `final-003` claiming it could not see store-specific overrides. They were merged into `misstated_capability` because one product change fixes both: constrain the agent's statements about itself to its actual nine tools. The merge test used throughout was whether fixing one behaviour would fix the other.

## A rejected group

Both annotations expected escalate_to_human for an above-threshold refund. ESC-1 states the refund tool itself queues the refund and the agent explains the result, so in final-059 issue_refund returned ok with an above-threshold note and the reply was accurate, and in final-060 the reply only described the policy. No requirement is violated, so the group was rejected rather than named.

## A rejected search suggestion and the boundary that excludes it

- `final-026` for `unsolicited_action_offer`: [unsolicited_action_offer] reply volunteers an extra action: 'Would you like me to'
- `final-054` for `unsolicited_action_offer`: [unsolicited_action_offer] reply volunteers an extra action: 'I can go ahead and'
- `final-049` for `tool_result_not_used`: [tool_result_not_used] get_order returned refund_eligible true and the reply still asks: 'Can you confirm'

The `unsolicited_action_offer` rejections set the boundary: a closing offer of further help is not an unrequested action. The mode requires the additional content to change the subject of the reply, as in `final-033`, where a shipping-status question was answered with an offer to cancel the order. The `tool_result_not_used` rejection on `final-049` sets a second boundary: a confirming question is only a failure when the tool result already settles the question being asked.

## Relationship to SPEC.md

Three modes map to existing requirements: `role_blind_reply` to RESP-4 and AUTH-1, `incorrect_eligibility_conclusion` to `cw-returns` and RESP-3, and `missed_escalation` to ESC-3.

The remaining five described behaviour the specification neither required nor forbade, so a revision was recorded before any label was assigned, as `spec_revision_tool_grounding`:

> The agent must ground statements about its own abilities and about record eligibility in its actual tool set and in the results those tools return. It must not request information a tool has already supplied, must not claim or deny an ability inconsistent with its tools, and must not perform a state-changing action the user has not requested.

The motivating annotations are on `final-016`, where `get_order` returned `refund_eligible` true and the reply asked the shopper for today's date, and `final-046`, where a refund executed although no user message requested one.
