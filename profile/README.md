# Homework 9: reducing cost

All agent runs use the Homework 8 development model, `openai/llama4-scout-17b-16e-instruct`, on the 8 development cases. Prices are in `optimize/config.json`.

## Part A: where cost comes from (`profile/results/costs.csv`)

| Category | Call site | Calls | Est. cost |
|---|---|---|---|
| customer conversation | `server/app.py:229` (Homework 3, Sonnet) | 851 | $4.88 |
| judge | `analysis/run_judges.py:180` (Homework 7 monitor, Maverick) | 140 | $0.095 |
| judge | `analysis/run_judges.py:179` at dcca46e (Homework 5, Maverick) | 120 | $0.076 |

Customer conversations cost about 30 times the judges combined, and 84% of their cost is input: tool definitions (about 887 tokens), the system prompt (about 369), and the growing conversation are re-sent on every call. No source saved token counts, so every count is a tiktoken estimate (`profile/scripts/cost_profile.py`). The course gateway also reports almost no input tokens for Claude (about 7 per run in Homework 8), so recorded Claude costs understate input.

## Part B: fewer tokens (reverted)

`search_help_center` returned two policy snippets instead of three. Score and `write_pass_5` were unchanged (0.975, 0.8), but input tokens rose 1.4% and cost rose 1.1% with flat latency: the development cases are mostly refund lookups that rarely search, so the shorter result saved little and run-to-run variation outweighed it. Reverted.

## Part C: prompt order for caching (kept)

The `## Session context` block moved to the end of `SYSTEM_PROMPT_TEMPLATE`, unchanged. Two users with the same role now share all but the last 19 characters of the system prompt, after the identical tool definitions: about 1,250 shared tokens. `cached_fraction` was 0.0 before and after, because the course gateway serves no OpenAI model and neither caches nor reports cached tokens for Scout (an identical 2,400-token prompt sent twice reported no cached tokens). The development score did not drop (0.975 to 1.0, within run-to-run variation), so the order was kept.

## Part D: judge cascade (accepted with caution)

Proxy: Scout with the frozen `missing_policy_citation_hw5-v1` prompt plus a confidence instruction (`cascade/run_proxy.py`). Oracle: the frozen judge's saved verdicts. Requirement, set before any proxy run: agreement with the oracle of at least 0.95.

- Development (40 labels): below a threshold of 0.95 the proxy handles everything with agreement 0.925 (3 disagreements); at 0.95 it handles 87.5% with agreement 1.000. Threshold 0.95, the lowest meeting the requirement, was locked before the test check.
- Test (40 labels, checked once): agreement 0.95 (2 disagreements), agreement with human labels 0.975, proxy share 95%, $0.455 per 1,000 verdicts against $0.621 for the oracle alone (27% less).
- Decision: accepted with caution. It meets the requirement exactly, with no margin, so one more disagreement would reject it; re-check it as more labels arrive.

## Part E: frontier (`profile/results/frontier.csv`)

`cache-after` (score 1.0, `write_pass_5` 1.0, $0.061 per 100 conversations, 1.40 s) is the only frontier configuration; `hw8-final`, `fewer-tokens`, and `cache-before` are dominated. Configuration chosen for use: `cache-after`. Its agent differs from `hw8-final` only in prompt order, so its edge in this run comes from run-to-run variation rather than caching.
