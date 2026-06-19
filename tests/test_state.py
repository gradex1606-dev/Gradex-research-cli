"""Tests for SQLModel models and repository methods."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

import gradex.state as state_module
from gradex.repository import ExperimentRepository, RunRepository

# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def repos(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[RunRepository, ExperimentRepository]:
    """Fresh in-memory DB under tmp_path, returned as (RunRepository, ExperimentRepository)."""
    evo_dir = tmp_path / ".gradex"
    monkeypatch.setattr(state_module, "GRADEX_DIR", evo_dir)
    monkeypatch.setattr(state_module, "DB_PATH", evo_dir / "state.db")
    return RunRepository(), ExperimentRepository()


# ---------------------------------------------------------------------------
# Run tests
# ---------------------------------------------------------------------------


def test_create_run(repos: tuple[RunRepository, ExperimentRepository]) -> None:
    """Creating a Run persists all fields and returns them correctly."""
    run_repo, _ = repos
    run = run_repo.create(
        benchmark_cmd="python bench.py",
        metric_direction="higher",
        gate_cmds=["pytest tests/"],
        baseline_score=42.0,
    )
    assert run.id  # UUID assigned
    assert run.benchmark_cmd == "python bench.py"
    assert run.metric_direction == "higher"
    assert run.baseline_score == 42.0
    assert run.get_gate_cmds() == ["pytest tests/"]

    # Round-trip via get()
    fetched = run_repo.get(run.id)
    assert fetched.id == run.id
    assert fetched.benchmark_cmd == run.benchmark_cmd


def test_get_latest_run(repos: tuple[RunRepository, ExperimentRepository]) -> None:
    """get_latest returns the most recently created Run."""
    run_repo, _ = repos
    run_repo.create("bench1", "higher", [], 1.0)
    time.sleep(0.01)  # ensure distinct created_at timestamps
    second = run_repo.create("bench2", "lower", [], 2.0)

    latest = run_repo.get_latest()
    assert latest is not None
    assert latest.id == second.id


def test_gate_cmds_serialization(
    repos: tuple[RunRepository, ExperimentRepository],
) -> None:
    """A list[str] round-trips correctly through the JSON gate_cmds column."""
    run_repo, _ = repos
    cmds = ["pytest tests/", "mypy src/", "ruff check ."]
    run = run_repo.create("bench", "higher", cmds, 0.0)
    fetched = run_repo.get(run.id)
    assert fetched.get_gate_cmds() == cmds


# ---------------------------------------------------------------------------
# Experiment tests
# ---------------------------------------------------------------------------


def test_create_experiment(
    repos: tuple[RunRepository, ExperimentRepository],
) -> None:
    """Creating an Experiment stores the run_id FK and defaults to 'pending'."""
    run_repo, exp_repo = repos
    run = run_repo.create("bench", "higher", [], 0.0)

    exp = exp_repo.create(run_id=run.id, parent_id=None, branch="feat/x")
    assert exp.id
    assert exp.run_id == run.id
    assert exp.parent_id is None
    assert exp.branch == "feat/x"
    assert exp.status == "pending"
    assert exp.score is None


def test_update_score(repos: tuple[RunRepository, ExperimentRepository]) -> None:
    """update_score persists score, gate_passed, and status correctly."""
    run_repo, exp_repo = repos
    run = run_repo.create("bench", "higher", [], 0.0)
    exp = exp_repo.create(run.id, None, "main")

    updated = exp_repo.update_score(
        exp.id, score=7.5, gate_passed=True, status="passed"
    )
    assert updated.score == 7.5
    assert updated.gate_passed is True
    assert updated.status == "passed"

    # Verify persistence
    fetched = exp_repo.get(exp.id)
    assert fetched.score == 7.5
    assert fetched.status == "passed"


def test_get_best_higher(repos: tuple[RunRepository, ExperimentRepository]) -> None:
    """get_best with direction='higher' returns the experiment with the max score."""
    run_repo, exp_repo = repos
    run = run_repo.create("bench", "higher", [], 0.0)

    for score in [1.0, 3.0, 2.0]:
        exp = exp_repo.create(run.id, None, "b")
        exp_repo.update_score(exp.id, score, True, "passed")

    best = exp_repo.get_best(run.id, "higher")
    assert best is not None
    assert best.score == 3.0


def test_get_best_lower(repos: tuple[RunRepository, ExperimentRepository]) -> None:
    """get_best with direction='lower' returns the experiment with the min score."""
    run_repo, exp_repo = repos
    run = run_repo.create("bench", "lower", [], 99.0)

    for score in [1.0, 3.0, 2.0]:
        exp = exp_repo.create(run.id, None, "b")
        exp_repo.update_score(exp.id, score, True, "passed")

    best = exp_repo.get_best(run.id, "lower")
    assert best is not None
    assert best.score == 1.0


def test_get_best_only_passed(
    repos: tuple[RunRepository, ExperimentRepository],
) -> None:
    """get_best ignores experiments whose status is not 'passed'."""
    run_repo, exp_repo = repos
    run = run_repo.create("bench", "higher", [], 0.0)

    # Two passing experiments
    for score in [1.0, 2.0]:
        exp = exp_repo.create(run.id, None, "b")
        exp_repo.update_score(exp.id, score, True, "passed")

    # Rejected experiment with a higher score — must not be selected
    rejected = exp_repo.create(run.id, None, "b")
    exp_repo.update_score(rejected.id, 999.0, False, "rejected")

    best = exp_repo.get_best(run.id, "higher")
    assert best is not None
    assert best.score == 2.0
