from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest

from harbor_adapter.analysis import analyze_capability_job
from harbor_adapter.export import _provider_key, export_tasks
from harbor_adapter.summary import _load_trial_results, summarize_job


def _write_cases(path: Path, cases: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(case) for case in cases) + "\n")


def _write_child_job(job: Path, rewards: list[float | None]) -> None:
    """Write a Harbor 0.23 job: aggregate result.json plus one child per trial."""
    job.mkdir()
    (job / "result.json").write_text(
        json.dumps({"id": "job", "n_total_trials": len(rewards), "stats": {}})
    )
    for attempt, reward in enumerate(rewards):
        trial_dir = job / f"e-001__trial{attempt}"
        trial_dir.mkdir()
        if reward is None:
            trial = {
                "task_name": "cartwheel/evals__e-001",
                "trial_name": trial_dir.name,
                "verifier_result": None,
                "exception_info": {"message": "sandbox failed"},
            }
        else:
            trial = {
                "task_name": "cartwheel/evals__e-001",
                "trial_name": trial_dir.name,
                "verifier_result": {"rewards": {"reward": reward}},
                "exception_info": None,
            }
        (trial_dir / "result.json").write_text(json.dumps(trial))
        # Deeper artifact results are not trial results and must be ignored.
        artifacts = trial_dir / "verifier"
        artifacts.mkdir()
        (artifacts / "result.json").write_text("not json")


def _unclassified_e001(path: Path) -> None:
    _write_cases(
        path,
        [
            {
                "id": "e-001",
                "mode": "cross_store_results_to_merchant",
                "input": {"role": "merchant", "user_id": 9001, "store_id": 1, "message": "hi"},
                "initial_state": {"world": "reseed", "fixture": None},
                "expected": {
                    "assertions": ["The lookup is denied."],
                    "checks": [{"check": "no_write_tools"}],
                },
            }
        ],
    )


def test_provider_key_follows_the_selected_model() -> None:
    assert _provider_key("gpt-example") == "OPENAI_API_KEY"
    assert _provider_key("o4-mini") == "OPENAI_API_KEY"
    assert _provider_key("anthropic/example") == "ANTHROPIC_API_KEY"
    assert _provider_key("openrouter/vendor-model") == "OPENROUTER_API_KEY"


def test_export_preserves_cartwheel_formats_and_builds_harbor_task(
    tmp_path: Path, monkeypatch
) -> None:
    state = tmp_path / "state"
    judges = state / "judges"
    judges.mkdir(parents=True)
    (judges / "response-quality-v1.json").write_text(
        json.dumps(
            {
                "judge_id": "response-quality-v1",
                "mode": "response-quality",
                "version": 1,
                "prompt_text": "The reply gives the information needed for the next step.",
                "model": "provider/frozen-judge-model",
                "status": "frozen",
            }
        )
    )
    monkeypatch.setenv("CARTWHEEL_ANALYSIS_STATE", str(state))
    cases_path = tmp_path / "cases.jsonl"
    case = {
        "id": "e-101",
        "mode": "response-quality",
        "kind": "capability",
        "baseline_pass_rate": 0.6,
        "input": {
            "role": "shopper",
            "user_id": 1,
            "message": "Can I return this order?",
        },
        "initial_state": {"world": "reseed", "fixture": None},
        "expected": {
            "assertions": ["The reply explains the next step."],
            "checks": [{"check": "tool_called", "name": "get_order"}],
            "judges": {"response-quality": "pass"},
        },
    }
    _write_cases(cases_path, [case])

    output = tmp_path / "tasks"
    tasks = export_tasks(cases_path, output, require_suite=False)

    assert tasks == [output / "e-101"]
    exported = json.loads(
        (output / "e-101" / "environment" / "cartwheel" / "case.json").read_text()
    )
    assert exported == case
    task = tomllib.loads((output / "e-101" / "task.toml").read_text())
    assert task["metadata"] == {
        "case_id": "e-101",
        "kind": "capability",
        "mode": "response-quality",
    }
    rubric = (output / "e-101" / "tests" / "judge_response-quality.py").read_text()
    compile(rubric, "judge_response-quality.py", "exec")
    assert "The reply gives the information needed for the next step." in rubric
    assert "MODEL = 'provider/frozen-judge-model'" in rubric
    assert "--- Trace to evaluate ---" in rubric
    assert '"critique": "string", "result": "string"' in rubric
    assert "judge_trace_text" in rubric
    assert (output / "e-101" / "tests" / "test.sh").stat().st_mode & 0o111
    assert "harbor-rewardkit==0.2.1" in (
        output / "e-101" / "tests" / "test.sh"
    ).read_text()
    assert "docetl==0.3.0" in (
        output / "e-101" / "tests" / "test.sh"
    ).read_text()
    assert not (output / "e-101" / "environment" / "cartwheel" / ".env").exists()


def test_baseline_export_accepts_only_unclassified_cases(tmp_path: Path) -> None:
    cases_path = tmp_path / "cases.jsonl"
    case = {
        "id": "e-102",
        "mode": "response_quality",
        "input": {"role": "shopper", "user_id": 1, "message": "hello"},
        "initial_state": {"world": "reseed", "fixture": None},
        "expected": {
            "assertions": ["The agent asks what the shopper needs."],
            "checks": [{"check": "reply_asks_question"}],
        },
    }
    _write_cases(cases_path, [case])
    output = tmp_path / "tasks"

    export_tasks(cases_path, output, baseline=True, case_ids={"e-102"})
    task = tomllib.loads((output / "e-102" / "task.toml").read_text())
    assert task["metadata"]["kind"] == "unclassified"

    with pytest.raises(ValueError, match="kind must be regression or capability"):
        export_tasks(cases_path, output, require_suite=False)


def test_summary_blocks_regressions_but_reports_capabilities(
    tmp_path: Path, monkeypatch
) -> None:
    import tests.eval.passk as passk

    def fake_case_passes(kind: str, passes: int, k: int, baseline_pass_rate=None):
        decision = "block" if kind == "regression" and passes < k else "pass"
        return {"decision": decision, "reason": "test"}

    monkeypatch.setattr(passk, "case_passes", fake_case_passes)
    monkeypatch.setattr(passk, "pass_at_k", lambda n, c, k: c / n)
    monkeypatch.setattr(passk, "pass_hat_k", lambda n, c, k: c / n)
    cases_path = tmp_path / "cases.jsonl"
    base = {
        "mode": "response_quality",
        "input": {"role": "shopper", "user_id": 1, "message": "hello"},
        "initial_state": {"world": "reseed", "fixture": None},
        "expected": {
            "assertions": ["The reply asks a question."],
            "checks": [{"check": "reply_asks_question"}],
        },
    }
    regression = {**base, "id": "e-201", "kind": "regression"}
    capability = {
        **base,
        "id": "e-202",
        "kind": "capability",
        "baseline_pass_rate": 0.4,
    }
    _write_cases(cases_path, [regression, capability])

    def trial(case_id: str, reward: float) -> dict:
        return {
            "task_name": f"cartwheel/evals__{case_id}",
            "verifier_result": {"rewards": {"reward": reward}},
            "exception_info": None,
        }

    job = tmp_path / "job"
    job.mkdir()
    trials = [trial("e-201", value) for value in [1, 1, 1, 1, 0]]
    trials += [trial("e-202", value) for value in [0, 0, 1, 0, 1]]
    (job / "result.json").write_text(json.dumps({"trial_results": trials}))

    markdown, passed = summarize_job(
        job, cases_path=cases_path, expected_attempts=5
    )

    assert passed is False
    assert "| `e-201` | regression | 4 | 5 | 0.800" in markdown
    assert "| `e-202` | capability | 2 | 5 | 0.400" in markdown


def test_baseline_summary_reports_the_observed_classification(tmp_path: Path) -> None:
    cases_path = tmp_path / "cases.jsonl"
    base = {
        "mode": "response_quality",
        "input": {"role": "shopper", "user_id": 1, "message": "hello"},
        "initial_state": {"world": "reseed", "fixture": None},
        "expected": {"checks": [{"check": "reply_asks_question"}]},
    }
    first = {**base, "id": "e-301"}
    second = {**base, "id": "e-302"}
    _write_cases(cases_path, [first, second])

    def trial(case_id: str, reward: float, attempt: int) -> dict:
        return {
            "task_name": f"cartwheel/evals__{case_id}",
            "trial_name": f"trial-{attempt}",
            "verifier_result": {"rewards": {"reward": reward}},
            "exception_info": None,
        }

    job = tmp_path / "job"
    job.mkdir()
    trials = [trial("e-301", 1, i) for i in range(5)]
    trials += [trial("e-302", value, i) for i, value in enumerate([1, 1, 1, 0, 0])]
    (job / "result.json").write_text(json.dumps({"trial_results": trials}))

    markdown, passed = summarize_job(
        job,
        cases_path=cases_path,
        expected_attempts=5,
        classify=True,
    )

    assert passed is True
    assert '`kind: "regression"`' in markdown
    assert '`kind: "capability"`, `baseline_pass_rate: 0.6`' in markdown


def test_baseline_summary_does_not_classify_infrastructure_errors(
    tmp_path: Path,
) -> None:
    cases_path = tmp_path / "cases.jsonl"
    case = {
        "id": "e-303",
        "mode": "response_quality",
        "input": {"role": "shopper", "user_id": 1, "message": "hello"},
        "initial_state": {"world": "reseed", "fixture": None},
        "expected": {"checks": [{"check": "reply_asks_question"}]},
    }
    _write_cases(cases_path, [case])
    job = tmp_path / "job"
    job.mkdir()
    trials = [
        {
            "task_name": "cartwheel/evals__e-303",
            "verifier_result": {"rewards": {"reward": 1}},
            "exception_info": None,
        }
        for _ in range(4)
    ]
    trials.append(
        {
            "task_name": "cartwheel/evals__e-303",
            "verifier_result": None,
            "exception_info": {"message": "sandbox failed"},
        }
    )
    (job / "result.json").write_text(json.dumps({"trial_results": trials}))

    markdown, passed = summarize_job(
        job,
        cases_path=cases_path,
        expected_attempts=5,
        classify=True,
    )

    assert passed is False
    assert "do not classify; complete five valid trials" in markdown


def test_embedded_trial_results_take_precedence_over_child_results(
    tmp_path: Path,
) -> None:
    job = tmp_path / "job"
    _write_child_job(job, [0.0])
    embedded = [{"task_name": "cartwheel/evals__e-001", "verifier_result": None}]
    (job / "result.json").write_text(json.dumps({"trial_results": embedded}))

    assert _load_trial_results(job) == embedded


def test_harbor_023_child_results_without_started_at_use_directory_order(
    tmp_path: Path,
) -> None:
    job = tmp_path / "job"
    _write_child_job(job, [1.0, 0.0, 1.0])

    trials = _load_trial_results(job)

    assert [trial["trial_name"] for trial in trials] == [
        "e-001__trial0",
        "e-001__trial1",
        "e-001__trial2",
    ]
    assert [trial["verifier_result"]["rewards"]["reward"] for trial in trials] == [
        1.0,
        0.0,
        1.0,
    ]


def test_harbor_023_five_passing_children_classify_as_regression(
    tmp_path: Path,
) -> None:
    cases_path = tmp_path / "cases.jsonl"
    _unclassified_e001(cases_path)
    job = tmp_path / "job"
    _write_child_job(job, [1.0] * 5)

    markdown, passed = summarize_job(
        job, cases_path=cases_path, expected_attempts=5, classify=True
    )

    assert passed is True
    assert '| `e-001` | 5 | 5 | `kind: "regression"` |' in markdown


def test_harbor_023_children_report_failures_and_missing_rewards(
    tmp_path: Path,
) -> None:
    cases_path = tmp_path / "cases.jsonl"
    _unclassified_e001(cases_path)

    failing = tmp_path / "failing"
    _write_child_job(failing, [1.0, 1.0, 0.0, 1.0, 1.0])
    markdown, passed = summarize_job(
        failing, cases_path=cases_path, expected_attempts=5, classify=True
    )
    assert passed is True
    assert '`kind: "capability"`, `baseline_pass_rate: 0.8`' in markdown

    errored = tmp_path / "errored"
    _write_child_job(errored, [1.0, 1.0, None, 1.0, 1.0])
    markdown, passed = summarize_job(
        errored, cases_path=cases_path, expected_attempts=5, classify=True
    )
    assert passed is False
    assert "do not classify; complete five valid trials" in markdown
    assert "e-001: 1 trial(s) did not produce a reward" in markdown


def test_malformed_child_result_names_its_path(tmp_path: Path) -> None:
    job = tmp_path / "job"
    _write_child_job(job, [1.0, 1.0])
    broken = job / "e-001__trial1" / "result.json"
    broken.write_text("{not json")

    with pytest.raises(ValueError, match=r"invalid Harbor trial result .*e-001__trial1"):
        _load_trial_results(job)


def test_final_export_requires_the_homework_suite(tmp_path: Path) -> None:
    cases_path = tmp_path / "cases.jsonl"
    base = {
        "mode": "first_mode",
        "kind": "regression",
        "input": {"role": "shopper", "user_id": 1, "message": "hello"},
        "initial_state": {"world": "reseed", "fixture": None},
        "expected": {
            "assertions": ["The reply asks a question."],
            "checks": [{"check": "reply_asks_question"}],
        },
    }
    cases = [{**base, "id": f"e-{index:03d}"} for index in range(10)]
    _write_cases(cases_path, cases)

    with pytest.raises(ValueError, match="at least two failure modes"):
        export_tasks(cases_path, tmp_path / "tasks")

    cases[-1] = {
        **cases[-1],
        "mode": "second_mode",
        "kind": "capability",
        "baseline_pass_rate": 0.8,
    }
    _write_cases(cases_path, cases)

    tasks = export_tasks(cases_path, tmp_path / "tasks")

    assert len(tasks) == 10


def test_capability_analysis_uses_5_10_and_15_observed_runs(
    tmp_path: Path, monkeypatch
) -> None:
    import tests.eval.passk as passk

    monkeypatch.setattr(passk, "pass_at_k", lambda n, c, k: (n + c + k) / 100)
    monkeypatch.setattr(
        "harbor_adapter.analysis.pass_at_k",
        lambda n, c, k: (n + c + k) / 100,
    )
    job = tmp_path / "job"
    job.mkdir()
    trials = []
    for attempt in range(14, -1, -1):
        trials.append(
            {
                "task_name": "cartwheel/evals__e-401",
                "trial_name": f"trial-{attempt:02d}",
                "verifier_result": {
                    "rewards": {"reward": 1 if attempt % 2 == 0 else 0}
                },
                "agent_info": {
                    "model_info": {
                        "provider": "student",
                        "name": "provider-model",
                    }
                },
                "exception_info": None,
            }
        )
    (job / "result.json").write_text(json.dumps({"trial_results": trials}))

    result = analyze_capability_job(job, "e-401")

    assert result["n"] == 15
    assert result["rewards"][:3] == [1, 0, 1]
    assert result["model"] == "student/provider-model"
    assert result["trials"][0]["trial_name"] == "trial-14"
    assert result["trial_order"] == "result.json trial_results order"
    assert [row["n"] for row in result["comparisons"]] == [5, 10, 15]
    assert set(result["comparisons"][-1]["pass_at_k"]) == {
        "1",
        "3",
        "5",
        "10",
        "15",
    }


def _capability_trial(
    case_id: str, trial_name: str, reward: float | None, *, error: bool = False
) -> dict:
    return {
        "task_name": f"cartwheel/evals__{case_id}",
        "trial_name": trial_name,
        "verifier_result": None if reward is None else {"rewards": {"reward": reward}},
        "agent_info": {"model_info": {"provider": "student", "name": "provider-model"}},
        "exception_info": {"message": "sandbox failed"} if error else None,
    }


def _write_capability_child_job(job: Path, trials: list[dict]) -> None:
    """Write a Harbor 0.23 job with one child result per trial, in list order."""
    job.mkdir()
    (job / "result.json").write_text(
        json.dumps({"id": "job", "n_total_trials": len(trials), "stats": {}})
    )
    for trial in trials:
        trial_dir = job / trial["trial_name"]
        trial_dir.mkdir()
        (trial_dir / "result.json").write_text(json.dumps(trial))
        # Deeper artifact results are not trial results and must be ignored.
        artifacts = trial_dir / "verifier"
        artifacts.mkdir()
        (artifacts / "result.json").write_text("not json")


@pytest.fixture
def stub_pass_at_k(monkeypatch) -> None:
    monkeypatch.setattr(
        "harbor_adapter.analysis.pass_at_k", lambda n, c, k: (n + c + k) / 100
    )


def test_capability_analysis_reads_harbor_023_child_results(
    tmp_path: Path, stub_pass_at_k
) -> None:
    from harbor_adapter.analysis import CHILD_ORDER

    # No started_at, so trials fall back to directory order; they are created
    # in reverse so that order differs from write order.
    trials = [
        _capability_trial("e-401", f"e-401__trial{i:02d}", 1 if i % 3 == 0 else 0)
        for i in range(14, -1, -1)
    ]
    # Another case's trials in the same job are filtered out by case id.
    trials.append(_capability_trial("e-402", "e-402__trial00", 1))
    job = tmp_path / "job"
    _write_capability_child_job(job, trials)

    result = analyze_capability_job(job, "e-401")

    assert result["n"] == 15
    assert [row["trial_name"] for row in result["trials"]] == [
        f"e-401__trial{i:02d}" for i in range(15)
    ]
    assert result["rewards"] == [1 if i % 3 == 0 else 0 for i in range(15)]
    assert result["successes"] == 5
    assert result["model"] == "student/provider-model"
    assert result["trial_order"] == CHILD_ORDER
    assert [row["successes"] for row in result["comparisons"]] == [2, 4, 5]
    assert analyze_capability_job(job, "e-401") == result


def test_capability_analysis_prefers_embedded_trial_results(
    tmp_path: Path, stub_pass_at_k
) -> None:
    from harbor_adapter.analysis import EMBEDDED_ORDER

    job = tmp_path / "job"
    _write_capability_child_job(job, [_capability_trial("e-401", "e-401__extra", 0)])
    embedded = [
        _capability_trial("e-401", f"trial-{i:02d}", 1) for i in range(14, -1, -1)
    ]
    (job / "result.json").write_text(json.dumps({"trial_results": embedded}))

    result = analyze_capability_job(job, "e-401")

    assert result["n"] == 15
    assert result["trials"][0]["trial_name"] == "trial-14"
    assert "e-401__extra" not in {row["trial_name"] for row in result["trials"]}
    assert result["trial_order"] == EMBEDDED_ORDER


@pytest.mark.parametrize(
    ("broken", "message"),
    [
        (dict(reward=None, error=True), "e-401__trial03 has an error"),
        (dict(reward=None), "e-401__trial03 has no reward"),
    ],
)
def test_capability_analysis_rejects_child_errors_and_missing_rewards(
    tmp_path: Path, stub_pass_at_k, broken: dict, message: str
) -> None:
    trials = [_capability_trial("e-401", f"e-401__trial{i:02d}", 1) for i in range(15)]
    trials[3] = _capability_trial("e-401", "e-401__trial03", **broken)
    job = tmp_path / "job"
    _write_capability_child_job(job, trials)

    with pytest.raises(ValueError, match=message):
        analyze_capability_job(job, "e-401")


def test_capability_analysis_counts_child_trials(
    tmp_path: Path, stub_pass_at_k
) -> None:
    job = tmp_path / "job"
    _write_capability_child_job(
        job, [_capability_trial("e-401", f"e-401__trial{i:02d}", 1) for i in range(5)]
    )

    with pytest.raises(ValueError, match="expected 15 trials, found 5"):
        analyze_capability_job(job, "e-401")
    assert analyze_capability_job(job, "e-401", expected_attempts=5)["n"] == 5


def _timed_trial(trial_name: str, started_at: object, reward: float = 1) -> dict:
    trial = _capability_trial("e-401", trial_name, reward)
    if started_at is not None:
        trial["started_at"] = started_at
    return trial


def _loaded_names(job: Path) -> list[str]:
    return [trial["trial_name"] for trial in _load_trial_results(job)]


def test_child_trials_load_in_started_at_order(tmp_path: Path) -> None:
    job = tmp_path / "job"
    _write_capability_child_job(
        job,
        [
            _timed_trial("e-401__aaa", "2026-10-13T20:18:00+00:00"),
            _timed_trial("e-401__bbb", "2026-10-13T20:19:00"),
            _timed_trial("e-401__ccc", "2026-10-13T20:17:45.338021Z"),
            _timed_trial("e-401__ddd", "2026-10-13T13:18:30-07:00"),
        ],
    )

    # 13:18:30-07:00 is 20:18:30Z; an offset-free timestamp is read as UTC.
    assert _loaded_names(job) == [
        "e-401__ccc",
        "e-401__aaa",
        "e-401__ddd",
        "e-401__bbb",
    ]


def test_child_trials_with_equal_started_at_use_directory_tiebreak(
    tmp_path: Path,
) -> None:
    job = tmp_path / "job"
    _write_capability_child_job(
        job,
        [
            _timed_trial("e-401__zzz", "2026-10-13T20:18:00Z"),
            _timed_trial("e-401__mmm", "2026-10-13T20:18:00Z"),
            _timed_trial("e-401__yyy", "2026-10-13T20:17:00Z"),
            _timed_trial("e-401__aaa", "2026-10-13T20:18:00+00:00"),
        ],
    )

    assert _loaded_names(job) == [
        "e-401__yyy",
        "e-401__aaa",
        "e-401__mmm",
        "e-401__zzz",
    ]


def test_child_trials_without_valid_started_at_follow_timestamped_trials(
    tmp_path: Path,
) -> None:
    job = tmp_path / "job"
    _write_capability_child_job(
        job,
        [
            _timed_trial("e-401__ccc", 1760386665),
            _timed_trial("e-401__bbb", "not a timestamp"),
            _timed_trial("e-401__aaa", None),
            _timed_trial("e-401__zzz", "2026-10-13T20:19:00Z"),
            _timed_trial("e-401__yyy", "2026-10-13T20:18:00Z"),
        ],
    )

    assert _loaded_names(job) == [
        "e-401__yyy",
        "e-401__zzz",
        "e-401__aaa",
        "e-401__bbb",
        "e-401__ccc",
    ]


def test_embedded_trial_results_keep_their_recorded_order(tmp_path: Path) -> None:
    job = tmp_path / "job"
    job.mkdir()
    embedded = [
        _timed_trial("trial-b", "2026-10-13T20:19:00Z"),
        _timed_trial("trial-c", None),
        _timed_trial("trial-a", "2026-10-13T20:17:00Z"),
    ]
    (job / "result.json").write_text(json.dumps({"trial_results": embedded}))

    assert _load_trial_results(job) == embedded


def test_child_trial_order_is_deterministic(tmp_path: Path) -> None:
    trials = [
        _timed_trial("e-401__qqq", "2026-10-13T20:18:00Z"),
        _timed_trial("e-401__ppp", "2026-10-13T20:18:00Z"),
        _timed_trial("e-401__rrr", None),
        _timed_trial("e-401__sss", "2026-10-13T20:17:00Z"),
    ]
    forward = tmp_path / "forward"
    backward = tmp_path / "backward"
    _write_capability_child_job(forward, trials)
    _write_capability_child_job(backward, list(reversed(trials)))

    expected = ["e-401__sss", "e-401__ppp", "e-401__qqq", "e-401__rrr"]
    assert _loaded_names(forward) == expected
    assert _loaded_names(forward) == expected
    assert _loaded_names(backward) == expected


def test_capability_analysis_uses_started_at_order(
    tmp_path: Path, stub_pass_at_k
) -> None:
    from harbor_adapter.analysis import CHILD_ORDER

    # Directory names run opposite to start times, so name order would reverse
    # the rewards. Only the first three trials (by start time) pass.
    trials = [
        _timed_trial(
            f"e-401__trial{14 - minute:02d}",
            f"2026-10-13T20:{minute:02d}:00Z",
            reward=1 if minute < 3 else 0,
        )
        for minute in range(15)
    ]
    job = tmp_path / "job"
    _write_capability_child_job(job, trials)

    result = analyze_capability_job(job, "e-401")

    assert [row["trial_name"] for row in result["trials"]] == [
        f"e-401__trial{14 - minute:02d}" for minute in range(15)
    ]
    assert result["rewards"] == [1, 1, 1] + [0] * 12
    assert [row["successes"] for row in result["comparisons"]] == [3, 3, 3]
    assert result["trial_order"] == CHILD_ORDER
    assert analyze_capability_job(job, "e-401") == result
