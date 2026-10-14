"""Bias-corrected failure prevalence for a monitoring period."""

from __future__ import annotations

from typing import Any, Sequence


def corrected_mode_prevalence(
    sample_preds: Sequence[int],
    test_labels: Sequence[int],
    test_preds: Sequence[int],
    confidence: float = 0.95,
    bootstrap_iterations: int = 20000,
    seed: int | None = 7,
) -> dict[str, Any]:
    """Bias-corrected live prevalence for one mode from sampled verdicts.

    The contract, precisely:

      1. ``raw`` is the uncorrected flag rate: ``mean(sample_preds)``.
      2. Compute the frozen judge's failure sensitivity and pass specificity
         from ``test_labels`` and ``test_preds``. Both use the monitoring
         convention that 1 means a failure is present. Failure sensitivity is
         the flagged fraction of human-labeled failures. Pass specificity is
         the unflagged fraction of human-labeled passes.
      3. Compute the Rogan-Gladen point estimate, then resample the held-out
         records and sampled predictions to obtain a percentile-bootstrap
         interval. Use a seeded NumPy generator so the committed result is
         reproducible.
      4. Resample the monitoring predictions and the paired held-out records
         independently with replacement. Keep their original sample sizes.
         Discard a draw if the correction cannot be computed. Clamp each
         retained estimate to [0, 1], then take the percentile interval.
         Raise ``ValueError`` if no replicate is valid.

    Args:
        sample_preds: the judge's 0/1 verdicts over the UNIFORM BASE sample
            only (never the risk strata; they are biased toward failure by
            design).
        test_labels: human labels for the frozen Homework 5 judge's test
            split.
        test_preds: the frozen judge's predictions on that test split.
        confidence: interval confidence level.
        bootstrap_iterations: number of percentile-bootstrap replicates.
        seed: numpy seed for a reproducible interval; None leaves the RNG
            untouched.

    Returns:
        {"raw", "corrected", "ci_low", "ci_high", "confidence",
         "failure_sensitivity", "pass_specificity", "n_sample"}
        with "corrected" clamped to [0, 1] and rates rounded to 4 places.

    Raises:
        ValueError: if an input is empty, the held-out inputs have different
            lengths, a value is not 0 or 1, a class is absent, the judge is
            missing a usable correction, or no bootstrap replicate is valid.
    """
    import numpy as np

    sample = np.asarray(list(sample_preds), dtype=int)
    labels = np.asarray(list(test_labels), dtype=int)
    preds = np.asarray(list(test_preds), dtype=int)
    if sample.size == 0 or labels.size == 0 or preds.size == 0:
        raise ValueError("sample_preds, test_labels, and test_preds must be nonempty")
    if labels.size != preds.size:
        raise ValueError("test_labels and test_preds must have the same length")
    for name, values in (("sample_preds", sample), ("test_labels", labels), ("test_preds", preds)):
        if not np.isin(values, (0, 1)).all():
            raise ValueError(f"{name} must contain only 0 and 1")
    if labels.sum() == 0 or labels.sum() == labels.size:
        raise ValueError("test_labels need both human-labeled failures and passes")

    def estimate(flags: np.ndarray, lab: np.ndarray, prd: np.ndarray) -> tuple[float, float, float] | None:
        failures, passes = lab == 1, lab == 0
        if not failures.any() or not passes.any():
            return None
        sensitivity = float((prd[failures] == 1).mean())
        specificity = float((prd[passes] == 0).mean())
        denominator = sensitivity + specificity - 1
        if denominator <= 0:
            return None
        raw_rate = float(flags.mean())
        return (raw_rate + specificity - 1) / denominator, sensitivity, specificity

    point = estimate(sample, labels, preds)
    if point is None:
        raise ValueError(
            "the judge has no usable correction: failure sensitivity + pass specificity <= 1"
        )
    corrected, sensitivity, specificity = point

    rng = np.random.default_rng(seed)
    sample_draws = rng.integers(0, sample.size, size=(bootstrap_iterations, sample.size))
    test_draws = rng.integers(0, labels.size, size=(bootstrap_iterations, labels.size))
    replicates = []
    for sample_index, test_index in zip(sample_draws, test_draws):
        result = estimate(sample[sample_index], labels[test_index], preds[test_index])
        if result is not None:
            replicates.append(min(1.0, max(0.0, result[0])))
    if not replicates:
        raise ValueError("no bootstrap replicate produced a usable correction")
    tail = (1 - confidence) / 2 * 100
    ci_low, ci_high = np.percentile(replicates, [tail, 100 - tail])

    return {
        "raw": round(float(sample.mean()), 4),
        "corrected": round(min(1.0, max(0.0, corrected)), 4),
        "ci_low": round(float(ci_low), 4),
        "ci_high": round(float(ci_high), 4),
        "confidence": confidence,
        "failure_sensitivity": round(sensitivity, 4),
        "pass_specificity": round(specificity, 4),
        "n_sample": int(sample.size),
    }
