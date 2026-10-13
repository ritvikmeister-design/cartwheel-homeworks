"""Edge cases for the HW6 pass@k, pass^k, and CI-decision helpers."""

from __future__ import annotations

import math

import pytest

from tests.eval.passk import case_passes, pass_at_k, pass_hat_k

ESTIMATORS = [pass_at_k, pass_hat_k]


@pytest.mark.parametrize("k", range(1, 6))
def test_zero_successes(k: int) -> None:
    assert pass_at_k(5, 0, k) == 0.0
    assert pass_hat_k(5, 0, k) == 0.0


@pytest.mark.parametrize("k", range(1, 6))
def test_all_successes(k: int) -> None:
    assert pass_at_k(5, 5, k) == 1.0
    assert pass_hat_k(5, 5, k) == 1.0


def test_k_equal_one_is_the_observed_pass_rate() -> None:
    assert pass_at_k(5, 3, 1) == pytest.approx(0.6)
    assert pass_hat_k(5, 3, 1) == pytest.approx(0.6)


def test_k_equal_n_needs_one_success_or_every_success() -> None:
    assert pass_at_k(5, 1, 5) == 1.0
    assert pass_at_k(5, 0, 5) == 0.0
    assert pass_hat_k(5, 4, 5) == 0.0
    assert pass_hat_k(5, 5, 5) == 1.0


def test_boundaries_return_exact_floats() -> None:
    # n - c < k for pass@k and c < k for pass^k.
    for value, expected in [(pass_at_k(8, 6, 4), 1.0), (pass_hat_k(8, 6, 8), 0.0)]:
        assert isinstance(value, float)
        assert value == expected


def test_combinatorial_estimates() -> None:
    assert pass_at_k(5, 3, 3) == pytest.approx(1 - math.comb(2, 3) / math.comb(5, 3))
    assert pass_at_k(5, 2, 2) == pytest.approx(1 - 3 / 10)
    assert pass_hat_k(5, 3, 2) == pytest.approx(3 / 10)
    assert isinstance(pass_at_k(5, 2, 2), float)
    assert isinstance(pass_hat_k(5, 3, 2), float)


@pytest.mark.parametrize("estimator", ESTIMATORS)
@pytest.mark.parametrize(
    ("n", "c", "k"),
    [
        (0, 0, 0),  # n < 1
        (0, 0, 1),
        (-1, 0, 1),
        (5, -1, 1),  # c outside [0, n]
        (5, 6, 1),
        (4, 5, 1),
        (5, 3, 0),  # k outside [1, n]
        (5, 3, 6),
        (5, 3, -1),
        (True, 1, 1),  # booleans are not run counts
        (5, True, 1),
        (5, 3, True),
        (5, False, 1),
        (5.0, 3, 1),  # non-integers
        (5, 3.0, 1),
        (5, 3, 1.0),
        ("5", 3, 1),
        (None, 3, 1),
    ],
)
def test_estimators_reject_invalid_arguments(estimator, n, c, k) -> None:
    with pytest.raises(ValueError):
        estimator(n, c, k)


def test_regression_passes_only_when_every_run_passes() -> None:
    result = case_passes("regression", 5, 5)
    assert result["decision"] == "pass"
    assert "5 of 5" in result["reason"]


@pytest.mark.parametrize("passes", range(0, 5))
def test_regression_blocks_on_any_failure(passes: int) -> None:
    result = case_passes("regression", passes, 5)
    assert result["decision"] == "block"
    assert f"failed {5 - passes} of 5" in result["reason"]


@pytest.mark.parametrize("passes", range(0, 6))
@pytest.mark.parametrize("baseline", [None, 0.0, 0.2, 0.6, 1.0])
def test_capability_always_passes(passes: int, baseline: float | None) -> None:
    result = case_passes("capability", passes, 5, baseline)
    assert result["decision"] == "pass"
    assert f"passed {passes} of 5" in result["reason"]
    assert "not blocking" in result["reason"]


def test_capability_reason_names_the_baseline() -> None:
    assert "baseline 0.6" in case_passes("capability", 2, 5, 0.6)["reason"]
    assert "no baseline" in case_passes("capability", 2, 5)["reason"]


@pytest.mark.parametrize("baseline", [None, 0.0, 0.6, 1.0])
def test_baseline_never_changes_the_decision(baseline: float | None) -> None:
    assert case_passes("regression", 4, 5, baseline)["decision"] == "block"
    assert case_passes("regression", 5, 5, baseline)["decision"] == "pass"
    assert case_passes("capability", 0, 5, baseline)["decision"] == "pass"


@pytest.mark.parametrize(
    "kind", ["Regression", "CAPABILITY", "capability ", "", "flaky", None, 1, ["regression"]]
)
def test_case_passes_rejects_invalid_kind(kind) -> None:
    with pytest.raises(ValueError):
        case_passes(kind, 5, 5)


@pytest.mark.parametrize(
    ("passes", "n"),
    [
        (-1, 5),  # passes outside [0, n]
        (6, 5),
        (0, 0),  # n < 1
        (1, -1),
        (True, 5),  # booleans are not run counts
        (5, True),
        (False, 5),
        (4.0, 5),  # non-integers
        (4, 5.0),
        ("4", 5),
    ],
)
def test_case_passes_rejects_invalid_counts(passes, n) -> None:
    for kind in ("regression", "capability"):
        with pytest.raises(ValueError):
            case_passes(kind, passes, n)


@pytest.mark.parametrize(
    "baseline", [-0.1, 1.1, 2, -1, math.nan, math.inf, -math.inf, True, False, "0.6"]
)
def test_case_passes_rejects_invalid_baseline(baseline) -> None:
    for kind in ("regression", "capability"):
        with pytest.raises(ValueError):
            case_passes(kind, 3, 5, baseline)
