"""Tests for Orchestrator — mocks SubagentRunner and BriefGenerator completely."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

import gradex.state as state_module
from gradex.ai.brief import BriefGenerator
from gradex.dashboard.broadcaster import DashboardBroadcaster
from gradex.orchestrator import Orchestrator, OrchestratorConfig
from gradex.repository import ExperimentRepository
from gradex.state import Run
from gradex.subagent import SubagentResult, SubagentRunner

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_broadcaster() -> None:
    """Fresh broadcaster singleton for every test."""
    DashboardBroadcaster.reset()
    yield  # type: ignore[misc]
    DashboardBroadcaster.reset()


@pytest.fixture
def db_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect DB to a tmp directory."""
    evo_dir = tmp_path / ".gradex"
    monkeypatch.setattr(state_module, "GRADEX_DIR", evo_dir)
    monkeypatch.setattr(state_module, "DB_PATH", evo_dir / "state.db")


@pytest.fixture
def mock_run() -> Run:
    return Run(
        id=str(uuid.uuid4()),
        benchmark_cmd="python bench.py",
        metric_direction="lower",
        gate_cmds="[]",
        baseline_score=41.2,
    )


@pytest.fixture
def mock_broadcaster() -> DashboardBroadcaster:
    b = AsyncMock(spec=DashboardBroadcaster)
    b.broadcast = AsyncMock()
    return b  # type: ignore[return-value]


@pytest.fixture
def mock_brief_gen() -> BriefGenerator:
    gen = MagicMock(spec=BriefGenerator)
    gen.generate.return_value = "brief text"
    return gen  # type: ignore[return-value]


@pytest.fixture
def mock_exp_repo() -> ExperimentRepository:
    """Mock repository that silently ignores updates."""
    repo = MagicMock(spec=ExperimentRepository)
    repo.update_score.return_value = None
    repo.list_by_run.return_value = []
    return repo  # type: ignore[return-value]


def make_subagent_result(
    score: float | None,
    gate_passed: bool,
    exp_id: str,
) -> SubagentResult:
    return SubagentResult(
        experiment_id=exp_id,
        score=score,
        gate_passed=gate_passed,
        hypothesis="test hypothesis",
        change_summary="changed something",
        error=None,
        duration_ms=100,
    )


def _make_orchestrator(
    mock_run: Run,
    mock_subagent: Any,
    mock_brief_gen: BriefGenerator,
    mock_broadcaster: DashboardBroadcaster,
    mock_exp_repo: ExperimentRepository,
    config: OrchestratorConfig | None = None,
) -> Orchestrator:
    if config is None:
        config = OrchestratorConfig(subagents=1, budget=5, stall=3)
    return Orchestrator(
        run=mock_run,
        subagent_runner=mock_subagent,
        brief_generator=mock_brief_gen,
        broadcaster=mock_broadcaster,
        config=config,
        exp_repo=mock_exp_repo,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_improvement_detected(
    mock_run: Run,
    mock_brief_gen: BriefGenerator,
    mock_broadcaster: DashboardBroadcaster,
    mock_exp_repo: ExperimentRepository,
    db_env: None,
) -> None:
    """First round returns an improvement → experiments_passed>=1, best_score=35.0."""
    exp_id = str(uuid.uuid4())
    mock_subagent = AsyncMock(spec=SubagentRunner)
    mock_subagent.run.return_value = make_subagent_result(35.0, True, exp_id)

    config = OrchestratorConfig(subagents=1, budget=10, stall=3)
    orch = _make_orchestrator(
        mock_run, mock_subagent, mock_brief_gen, mock_broadcaster, mock_exp_repo, config
    )
    result = await orch.run()

    assert result.experiments_passed >= 1
    assert result.best_score == pytest.approx(35.0)


@pytest.mark.anyio
async def test_stall_stops_loop(
    mock_run: Run,
    mock_brief_gen: BriefGenerator,
    mock_broadcaster: DashboardBroadcaster,
    mock_exp_repo: ExperimentRepository,
    db_env: None,
) -> None:
    """All subagents return a regression → stall counter reaches limit."""
    mock_subagent = AsyncMock(spec=SubagentRunner)
    mock_subagent.run.return_value = make_subagent_result(45.0, True, str(uuid.uuid4()))

    config = OrchestratorConfig(subagents=1, budget=10, stall=2)
    orch = _make_orchestrator(
        mock_run, mock_subagent, mock_brief_gen, mock_broadcaster, mock_exp_repo, config
    )
    result = await orch.run()

    assert result.stopped_reason == "stall"
    assert result.rounds_completed == 2


@pytest.mark.anyio
async def test_gate_failure_rejected(
    mock_run: Run,
    mock_brief_gen: BriefGenerator,
    mock_broadcaster: DashboardBroadcaster,
    mock_exp_repo: ExperimentRepository,
    db_env: None,
) -> None:
    """Score improvement but gate_passed=False → not promoted."""
    mock_subagent = AsyncMock(spec=SubagentRunner)
    mock_subagent.run.return_value = make_subagent_result(
        30.0, False, str(uuid.uuid4())
    )

    config = OrchestratorConfig(subagents=1, budget=10, stall=1)
    orch = _make_orchestrator(
        mock_run, mock_subagent, mock_brief_gen, mock_broadcaster, mock_exp_repo, config
    )
    result = await orch.run()

    assert result.experiments_passed == 0
    assert result.best_score is None or result.best_score == pytest.approx(41.2)


@pytest.mark.anyio
async def test_budget_stops_loop(
    mock_run: Run,
    mock_brief_gen: BriefGenerator,
    mock_broadcaster: DashboardBroadcaster,
    mock_exp_repo: ExperimentRepository,
    db_env: None,
) -> None:
    """Budget exhausted after subagents × budget experiments."""
    scores = iter([38.0, 37.0, 36.0, 35.0])

    async def _side_effect(*args: object, **kwargs: object) -> SubagentResult:
        return make_subagent_result(next(scores), True, str(uuid.uuid4()))

    mock_subagent = AsyncMock(spec=SubagentRunner)
    mock_subagent.run.side_effect = _side_effect

    config = OrchestratorConfig(subagents=2, budget=2, stall=99)
    orch = _make_orchestrator(
        mock_run, mock_subagent, mock_brief_gen, mock_broadcaster, mock_exp_repo, config
    )
    result = await orch.run()

    assert result.stopped_reason == "budget"
    assert result.total_experiments <= 4


@pytest.mark.anyio
async def test_exception_from_subagent_handled(
    mock_run: Run,
    mock_brief_gen: BriefGenerator,
    mock_broadcaster: DashboardBroadcaster,
    mock_exp_repo: ExperimentRepository,
    db_env: None,
) -> None:
    """Subagent raises an exception — orchestrator must not propagate it."""
    mock_subagent = AsyncMock(spec=SubagentRunner)
    mock_subagent.run.side_effect = RuntimeError("agent crashed")

    config = OrchestratorConfig(subagents=1, budget=1, stall=1)
    orch = _make_orchestrator(
        mock_run, mock_subagent, mock_brief_gen, mock_broadcaster, mock_exp_repo, config
    )
    result = await orch.run()

    assert result.stopped_reason in ("stall", "budget", "error")


@pytest.mark.anyio
async def test_broadcast_called_per_experiment(
    mock_run: Run,
    mock_brief_gen: BriefGenerator,
    mock_broadcaster: DashboardBroadcaster,
    mock_exp_repo: ExperimentRepository,
    db_env: None,
) -> None:
    """broadcast() is called at least once per experiment in the round."""
    mock_subagent = AsyncMock(spec=SubagentRunner)
    mock_subagent.run.return_value = make_subagent_result(45.0, True, str(uuid.uuid4()))

    config = OrchestratorConfig(subagents=3, budget=1, stall=1)
    orch = _make_orchestrator(
        mock_run, mock_subagent, mock_brief_gen, mock_broadcaster, mock_exp_repo, config
    )
    await orch.run()

    # At least one broadcast per experiment (experiment_update events)
    assert mock_broadcaster.broadcast.call_count >= 3  # type: ignore[attr-defined]


@pytest.mark.anyio
async def test_higher_is_better_direction(
    mock_brief_gen: BriefGenerator,
    mock_broadcaster: DashboardBroadcaster,
    mock_exp_repo: ExperimentRepository,
    db_env: None,
) -> None:
    """metric_direction='higher': score above baseline is treated as improvement."""
    run = Run(
        id=str(uuid.uuid4()),
        benchmark_cmd="python bench.py",
        metric_direction="higher",
        gate_cmds="[]",
        baseline_score=10.0,
    )
    exp_id = str(uuid.uuid4())
    mock_subagent = AsyncMock(spec=SubagentRunner)
    mock_subagent.run.return_value = make_subagent_result(15.0, True, exp_id)

    config = OrchestratorConfig(subagents=1, budget=10, stall=3)
    orch = _make_orchestrator(
        run, mock_subagent, mock_brief_gen, mock_broadcaster, mock_exp_repo, config
    )
    result = await orch.run()

    assert result.experiments_passed >= 1
    assert result.best_score == pytest.approx(15.0)
