# Homework 7 monitoring: missing_policy_citation

Judge `missing_policy_citation_hw5-v1` (frozen Homework 5 judge, Llama 4 Maverick), Cartwheel model `openai/claude-5-sonnet-gosys`, the 50 scenarios in `scenarios/monitoring_scenarios.jsonl` in each period, random rate 0.2 (10 conversations), risk groups `policy_lookup` and `multi_turn`, and a threshold of 0.15 chosen before either period was judged. The judge's held-out test metrics are failure sensitivity 1.00 (7/7) and pass specificity 0.97 (32/33).

| Period | Window (UTC) | Traces | Random flagged | Raw | Corrected | 95% interval |
|---|---|---|---|---|---|---|
| before (Homework 3 run) | 2026-10-09 20:01-20:47 | 74 | 1/10 | 0.10 | 0.072 | 0.00-0.30 |
| after (new run) | 2026-10-14 03:38-03:49 | 74 | 2/10 | 0.20 | 0.175 | 0.00-0.47 |

## 1. Did the corrected failure estimate move between the two periods?

The point estimate rose from 0.072 to 0.175. The entire change comes from one additional flagged conversation in a random sample of 10 (1/10 before, 2/10 after).

## 2. Do the intervals support a conclusion, or is the result uncertain?

The result is uncertain. The two intervals (0.00-0.30 and 0.00-0.47) overlap almost completely, and both contain zero and the 0.15 threshold. The after estimate sits above the threshold, but this data cannot separate a real increase from sampling noise. With only 10 random conversations per period, most of the interval width comes from the small sample, and the judge's held-out uncertainty adds to it.

## 3. What did the risk groups reveal that the random estimate did not?

The risk groups found most of the failures. Six of the seven flagged conversations before, and five of the seven after, were outside the random sample. Multi-turn conversations were flagged at 6/22 and 5/22, and policy-lookup conversations at 3/19 and 4/21, compared with 1/10 and 2/10 in the random sample. Four scenarios were flagged in both periods (final-036, final-050, final-224, final-235), which suggests recurring cases rather than one-off noise. These group rates are not prevalence estimates, because the groups were selected for risk rather than sampled at random.

## 4. What action should happen if the estimate crosses the threshold?

A crossing should start error analysis on the flagged traces from both the random sample and the risk groups. Each flag should be confirmed with a human label, and confirmed failures should become new Homework 6 evaluation cases, classified by five baseline runs. Here the after estimate crossed 0.15 with an interval that spans it, so the first step is to review the seven flagged after-period traces and the four recurring scenarios, and to enlarge the random sample before treating the rate itself as established.

## Scheduled monitor

`.github/workflows/monitor.yml` runs `uv run python -m monitoring.run --last-hours 24` daily at 06:17 UTC and on manual dispatch, and uploads `monitoring/output/` as an artifact even when the job fails. Langfuse runs locally and the frozen judge is served through a gateway that only this laptop can reach, so the job targets a self-hosted runner. The workflow file is also on `main`, because scheduled and manual runs start from the default branch; it checks out `homework-7`, where the monitoring code lives.

The manual run [38511489046](https://github.com/ritvikmeister-design/cartwheel-homeworks/actions/runs/38511489046) completed on a temporary runner. It found the 50 after-period conversations in the last 24 hours, judged 32 of them (a 10-conversation random sample plus 28 in the risk groups), and wrote 39 scores. Raw rate 0.10, corrected 0.072 [0.00, 0.30]. Its random sample differs from the after period's because a recent window groups traces by session id rather than scenario id. The runner was removed after the run, so later scheduled runs wait for a runner. An empty window records a zero count and exits without calling the judge.

## Langfuse dashboard

The dashboard `HW7 missing_policy_citation monitor` shows the average `missing_policy_citation_verdict` (random sample) over time, the average `missing_policy_citation_risk_verdict` over time, and a table of traces where either verdict is 1. Verdict scores are dated at their conversation and each corrected-prevalence score at its period end, so the before and after periods appear on their own dates.

## Implementation notes

- The judge receives each conversation rendered exactly as its Homework 5 inputs were built. The rendering was checked to be identical on the 80 Homework 5 sessions still in Langfuse. The call uses the validated Homework 5 gateway request, message layout, and VERDICT parser rather than a DocETL wrapper.
- A period is rejected if any of the 50 scenario ids is missing, if a scenario has more than one session, or if an eligible trace uses a different Cartwheel model.
- Score identifiers are stable. Rerunning the after period updated the existing 39 scores without creating duplicates, and all 36 verdicts were unchanged.
- Langfuse rejects a score with no target, so each period's corrected-prevalence score is attached to a session named `hw7-monitor-<label>`.
