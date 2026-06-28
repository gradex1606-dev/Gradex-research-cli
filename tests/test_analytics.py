"""Tests for gradex.analytics — RunAnalytics and related dataclasses."""

from __future__ import annotations

import pytest

import gradex.state as state_module

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def seeded_run(tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch):  # type: ignore[type-arg]
    """Create a run with 7 experiments: 3 passed, 2 rejected, 2 failed."""
    gradex_dir = tmp_path / ".gradex"
    monkeypatch.setattr(state_module, "GRADEX_DIR", gradex_dir)
    monkeypatch.setattr(state_module, "DB_PATH", gradex_dir / "state.db")

    from gradex.repository import ExperimentRepository, RunRepository

    run_repo = RunRepository()
    exp_repo = ExperimentRepository()

    run = run_repo.create("python bench.py", "lower", ["pytest tests/"], 41.2)
    experiments = [
        ("passed", 38.1, True),
        ("rejected", 29.0, False),
        ("passed", 35.6, True),
        ("failed", None, None),
        ("passed", 31.4, True),
        ("rejected", 28.0, False),
        ("failed", None, None),
    ]
    for status, score, gate in experiments:
        exp = exp_repo.create(run.id, None, "gradex/exp")
        if score is not None and gate is not None:
            exp_repo.update_score(exp.id, score, gate, status)
        elif status in ("failed",):
            # Update status without a score by setting score=0 then overriding status
            # (update_score requires a float; use 0.0 and then set failed status)
            from sqlmodel import Session

            from gradex.state import Experiment, get_engine

            with Session(get_engine()) as session:
                result = session.exec(
                    __import__("sqlmodel")
                    .select(Experiment)
                    .where(Experiment.id == exp.id)
                )
                db_exp = result.one()
                db_exp.status = "failed"
                session.add(db_exp)
                session.commit()

    return run


@pytest.fixture()
def fresh_db(tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch):  # type: ignore[type-arg]
    """Empty database in a temp directory."""
    gradex_dir = tmp_path / ".gradex"
    monkeypatch.setattr(state_module, "GRADEX_DIR", gradex_dir)
    monkeypatch.setattr(state_module, "DB_PATH", gradex_dir / "state.db")


# ---------------------------------------------------------------------------
# Breakdown & pass rate
# ---------------------------------------------------------------------------


def test_breakdown_counts(seeded_run) -> None:  # type: ignore[no-untyped-def]
    from gradex.analytics import RunAnalytics

    summary = RunAnalytics().get_run_summary(seeded_run.id)
    assert summary.breakdown.total == 7
    assert summary.breakdown.passed == 3
    assert summary.breakdown.rejected == 2
    assert summary.breakdown.failed == 2


def test_pass_rate(seeded_run) -> None:  # type: ignore[no-untyped-def]
    from gradex.analytics import RunAnalytics

    summary = RunAnalytics().get_run_summary(seeded_run.id)
    # completed = 3+2+2=7, passed=3 → 42.9%
    assert summary.breakdown.pass_rate == 42.9


# ---------------------------------------------------------------------------
# Best score & improvement
# ---------------------------------------------------------------------------


def test_best_score_lower_is_better(seeded_run) -> None:  # type: ignore[no-untyped-def]
    from gradex.analytics import RunAnalytics

    summary = RunAnalytics().get_run_summary(seeded_run.id)
    # passed scores: 38.1, 35.6, 31.4 → best for lower = 31.4
    assert summary.best_score == 31.4


def test_improvement_pct(seeded_run) -> None:  # type: ignore[no-untyped-def]
    from gradex.analytics import RunAnalytics

    summary = RunAnalytics().get_run_summary(seeded_run.id)
    # baseline=41.2, best=31.4, direction=lower
    # abs_delta = 41.2 - 31.4 = 9.8  →  pct = 9.8/41.2*100 = 23.8%
    assert summary.improvement_pct == 23.8
    assert summary.improvement_abs == 9.8


def test_improvement_positive_means_better(seeded_run) -> None:  # type: ignore[no-untyped-def]
    from gradex.analytics import RunAnalytics

    summary = RunAnalytics().get_run_summary(seeded_run.id)
    # lower-is-better, we achieved a lower score → improvement > 0
    assert summary.improvement_pct is not None
    assert summary.improvement_pct > 0


# ---------------------------------------------------------------------------
# Score over time
# ---------------------------------------------------------------------------


def test_score_over_time_sorted(seeded_run) -> None:  # type: ignore[no-untyped-def]
    from gradex.analytics import RunAnalytics

    points = RunAnalytics().get_score_over_time(seeded_run.id)
    assert len(points) == 3  # only passed experiments
    assert all(p.score for p in points)
    # First point has no delta_from_previous
    assert points[0].delta_from_previous is None
    assert points[1].delta_from_previous is not None


def test_score_over_time_delta_from_baseline(seeded_run) -> None:  # type: ignore[no-untyped-def]
    from gradex.analytics import RunAnalytics

    points = RunAnalytics().get_score_over_time(seeded_run.id)
    # All points should have delta_from_baseline set
    for pt in points:
        assert pt.delta_from_baseline is not None
    # For lower-is-better: all passed scores < baseline=41.2 → delta < 0
    assert all(pt.delta_from_baseline < 0 for pt in points)


# ---------------------------------------------------------------------------
# get_all_runs
# ---------------------------------------------------------------------------


def test_get_all_runs_returns_ordered(
    tmp_path: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,  # type: ignore[type-arg]
) -> None:
    gradex_dir = tmp_path / ".gradex"
    monkeypatch.setattr(state_module, "GRADEX_DIR", gradex_dir)
    monkeypatch.setattr(state_module, "DB_PATH", gradex_dir / "state.db")

    from gradex.analytics import RunAnalytics
    from gradex.repository import RunRepository

    run_repo = RunRepository()
    run_repo.create("cmd1", "lower", [], 10.0)
    run_repo.create("cmd2", "lower", [], 20.0)
    run_repo.create("cmd3", "lower", [], 30.0)

    runs = RunAnalytics().get_all_runs(limit=3)
    assert len(runs) == 3
    # Newest first
    assert runs[0].created_at >= runs[1].created_at
    assert runs[1].created_at >= runs[2].created_at


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_no_experiments_run(
    tmp_path: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,  # type: ignore[type-arg]
) -> None:
    gradex_dir = tmp_path / ".gradex"
    monkeypatch.setattr(state_module, "GRADEX_DIR", gradex_dir)
    monkeypatch.setattr(state_module, "DB_PATH", gradex_dir / "state.db")

    from gradex.analytics import RunAnalytics
    from gradex.repository import RunRepository

    run = RunRepository().create("python bench.py", "lower", [], 41.2)
    summary = RunAnalytics().get_run_summary(run.id)
    assert summary.breakdown.total == 0
    assert summary.best_score is None
    assert summary.improvement_pct is None
    assert summary.breakdown.pass_rate == 0.0


def test_higher_is_better_improvement(
    tmp_path: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,  # type: ignore[type-arg]
) -> None:
    gradex_dir = tmp_path / ".gradex"
    monkeypatch.setattr(state_module, "GRADEX_DIR", gradex_dir)
    monkeypatch.setattr(state_module, "DB_PATH", gradex_dir / "state.db")

    from gradex.analytics import RunAnalytics
    from gradex.repository import ExperimentRepository, RunRepository

    run = RunRepository().create("python bench.py", "higher", [], 10.0)
    exp = ExperimentRepository().create(run.id, None, "gradex/exp")
    ExperimentRepository().update_score(exp.id, 15.0, True, "passed")

    summary = RunAnalytics().get_run_summary(run.id)
    assert summary.improvement_pct == 50.0
    assert summary.improvement_abs == 5.0


def test_run_summary_short_id(seeded_run) -> None:  # type: ignore[no-untyped-def]
    from gradex.analytics import RunAnalytics

    summary = RunAnalytics().get_run_summary(seeded_run.id)
    assert summary.run_id_short == seeded_run.id[:8]
    assert len(summary.run_id_short) == 8


def test_token_usage_aggregation(
    tmp_path: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,  # type: ignore[type-arg]
) -> None:
    gradex_dir = tmp_path / ".gradex"
    monkeypatch.setattr(state_module, "GRADEX_DIR", gradex_dir)
    monkeypatch.setattr(state_module, "DB_PATH", gradex_dir / "state.db")

    from gradex.analytics import RunAnalytics
    from gradex.repository import ExperimentRepository, RunRepository

    run = RunRepository().create("python bench.py", "lower", [], 10.0)
    exp = ExperimentRepository().create(run.id, None, "gradex/a")
    ExperimentRepository().update_llm_usage(exp.id, 1000, 200, "llama-3.3-70b-versatile")
    ExperimentRepository().update_score(exp.id, 8.0, True, "passed")

    summary = RunAnalytics().get_run_summary(run.id)
    assert summary.total_input_tokens == 1000
    assert summary.total_output_tokens == 200
    assert summary.llm_call_count == 1
    assert summary.estimated_cost_usd == 0.0

