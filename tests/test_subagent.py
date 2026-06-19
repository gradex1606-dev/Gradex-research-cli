"""Tests for SubagentRunner — mocks Backend, BenchmarkRunner, GateRunner, LLMClient."""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

import gradex.state as state_module
from gradex.ai.client import LLMClient, LLMResponse
from gradex.backends.base import Backend
from gradex.dashboard.broadcaster import DashboardBroadcaster
from gradex.runner.benchmark import BenchmarkResult, BenchmarkRunner
from gradex.runner.gate import GateResult, GateRunner
from gradex.state import Run
from gradex.subagent import SubagentRunner

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
    """Redirect DB to a temporary directory."""
    evo_dir = tmp_path / ".gradex"
    monkeypatch.setattr(state_module, "GRADEX_DIR", evo_dir)
    monkeypatch.setattr(state_module, "DB_PATH", evo_dir / "state.db")


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """Return a real writable workspace directory."""
    ws = tmp_path / "workspace"
    ws.mkdir()
    return ws


@pytest.fixture
def mock_run() -> Run:
    return Run(
        id=str(uuid.uuid4()),
        benchmark_cmd="python bench.py",
        metric_direction="lower",
        gate_cmds="[]",
        baseline_score=41.2,
    )


def _make_llm_client(response_text: str) -> LLMClient:
    """Return an LLMClient whose complete() always returns *response_text*."""
    client = AsyncMock(spec=LLMClient)
    client.complete.return_value = LLMResponse(
        text=response_text,
        input_tokens=10,
        output_tokens=20,
        provider="mock",
        model="mock",
    )
    return client  # type: ignore[return-value]


def _make_backend(
    workspace_path: Path, raise_on_run: Exception | None = None
) -> Backend:
    """Return a mock Backend that uses *workspace_path* as its workspace."""
    backend = AsyncMock(spec=Backend)
    backend.create_workspace.return_value = workspace_path
    if raise_on_run is not None:
        backend.run_command.side_effect = raise_on_run
    return backend  # type: ignore[return-value]


def _make_benchmark_runner(
    score: float | None = 35.0,
    timed_out: bool = False,
    raise_exc: Exception | None = None,
) -> BenchmarkRunner:
    runner = AsyncMock(spec=BenchmarkRunner)
    if raise_exc is not None:
        runner.run.side_effect = raise_exc
    else:
        runner.run.return_value = BenchmarkResult(
            score=score,
            stdout="35.0",
            stderr="",
            duration_ms=100,
            timed_out=timed_out,
            parse_error="Command timed out" if timed_out else None,
        )
    return runner  # type: ignore[return-value]


def _make_gate_runner(passed: bool = True) -> GateRunner:
    runner = AsyncMock(spec=GateRunner)
    runner.run.return_value = GateResult(
        passed=passed,
        failures=[] if passed else ["pytest: exit code 1"],
        duration_ms=50,
    )
    return runner  # type: ignore[return-value]


_VALID_JSON = (
    '{"file": "src/parser.py", "new_content": "def parse(): return 1", '
    '"hypothesis": "simplify parse", "change_summary": "removed loop"}'
)


def _make_runner(
    workspace_path: Path,
    mock_run: Run,
    llm_text: str = _VALID_JSON,
    benchmark_score: float | None = 35.0,
    benchmark_timed_out: bool = False,
    gate_passed: bool = True,
    benchmark_raise: Exception | None = None,
) -> SubagentRunner:
    return SubagentRunner(
        backend=_make_backend(workspace_path),
        benchmark_runner=_make_benchmark_runner(
            score=benchmark_score,
            timed_out=benchmark_timed_out,
            raise_exc=benchmark_raise,
        ),
        gate_runner=_make_gate_runner(gate_passed),
        llm_client=_make_llm_client(llm_text),
        run=mock_run,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_experiment_uses_orchestrator_assigned_id(
    workspace: Path, mock_run: Run, db_env: None
) -> None:
    """Experiment row must use the ID passed in by the orchestrator."""
    from gradex.repository import ExperimentRepository

    exp_id = str(uuid.uuid4())
    runner = _make_runner(workspace, mock_run)
    await runner.run(exp_id, None, "brief text", 0)

    exp = ExperimentRepository().get(exp_id)
    assert exp.id == exp_id
    assert exp.status == "running"


@pytest.mark.anyio
async def test_successful_experiment(
    workspace: Path, mock_run: Run, db_env: None
) -> None:
    """Happy path: valid LLM JSON → score=35.0, gate passed, no error."""
    runner = _make_runner(workspace, mock_run)
    result = await runner.run(str(uuid.uuid4()), None, "brief text", 0)

    assert result.score == pytest.approx(35.0)
    assert result.gate_passed is True
    assert result.error is None
    assert result.hypothesis == "simplify parse"
    assert result.change_summary == "removed loop"


@pytest.mark.anyio
async def test_llm_json_parse_failure(
    workspace: Path, mock_run: Run, db_env: None
) -> None:
    """Non-JSON LLM response → error set, score None, workspace cleaned up."""
    backend = _make_backend(workspace)
    runner = SubagentRunner(
        backend=backend,
        benchmark_runner=_make_benchmark_runner(),
        gate_runner=_make_gate_runner(),
        llm_client=_make_llm_client("not json at all"),
        run=mock_run,
    )
    result = await runner.run(str(uuid.uuid4()), None, "brief", 0)

    assert result.error is not None
    assert result.score is None
    backend.cleanup_workspace.assert_called_once()  # type: ignore[attr-defined]


@pytest.mark.anyio
async def test_llm_json_with_fences(
    workspace: Path, mock_run: Run, db_env: None
) -> None:
    """Markdown-fenced JSON is stripped and parsed correctly."""
    fenced = f"```json\n{_VALID_JSON}\n```"
    runner = _make_runner(workspace, mock_run, llm_text=fenced)
    result = await runner.run(str(uuid.uuid4()), None, "brief", 0)

    assert result.error is None
    assert result.score == pytest.approx(35.0)


@pytest.mark.anyio
async def test_gate_failure_propagated(
    workspace: Path, mock_run: Run, db_env: None
) -> None:
    """Gate failure is reflected in result but is NOT an error."""
    runner = _make_runner(workspace, mock_run, gate_passed=False)
    result = await runner.run(str(uuid.uuid4()), None, "brief", 0)

    assert result.gate_passed is False
    assert result.error is None
    assert result.score == pytest.approx(35.0)


@pytest.mark.anyio
async def test_benchmark_timeout(workspace: Path, mock_run: Run, db_env: None) -> None:
    """Timed-out benchmark → score=None and error reflects the timeout."""
    runner = _make_runner(
        workspace, mock_run, benchmark_score=None, benchmark_timed_out=True
    )
    result = await runner.run(str(uuid.uuid4()), None, "brief", 0)

    assert result.score is None
    assert result.error is not None
    assert "timed out" in result.error.lower()


@pytest.mark.anyio
async def test_workspace_cleaned_on_exception(
    workspace: Path, mock_run: Run, db_env: None
) -> None:
    """When the benchmark runner raises, the workspace is still cleaned up."""
    backend = _make_backend(workspace)
    runner = SubagentRunner(
        backend=backend,
        benchmark_runner=_make_benchmark_runner(
            raise_exc=RuntimeError("backend crash")
        ),
        gate_runner=_make_gate_runner(),
        llm_client=_make_llm_client(_VALID_JSON),
        run=mock_run,
    )
    result = await runner.run(str(uuid.uuid4()), None, "brief", 0)

    assert result.error is not None
    backend.cleanup_workspace.assert_called()  # type: ignore[attr-defined]


@pytest.mark.anyio
async def test_parse_llm_json_missing_key(
    workspace: Path, mock_run: Run, db_env: None
) -> None:
    """Valid JSON missing 'new_content' → _parse_llm_json raises, run returns error."""
    bad_json = '{"file": "foo.py", "hypothesis": "h", "change_summary": "s"}'
    runner = _make_runner(workspace, mock_run, llm_text=bad_json)
    result = await runner.run(str(uuid.uuid4()), None, "brief", 0)

    assert result.error is not None
    assert result.score is None


# ---------------------------------------------------------------------------
# _parse_llm_json unit tests (direct method calls)
# ---------------------------------------------------------------------------


def test_parse_valid_json(workspace: Path, mock_run: Run) -> None:
    runner = _make_runner(workspace, mock_run)
    parsed = runner._parse_llm_json(_VALID_JSON)
    assert parsed["file"] == "src/parser.py"
    assert parsed["hypothesis"] == "simplify parse"


def test_parse_fenced_json(workspace: Path, mock_run: Run) -> None:
    fenced = f"```json\n{_VALID_JSON}\n```"
    runner = _make_runner(workspace, mock_run)
    parsed = runner._parse_llm_json(fenced)
    assert parsed["file"] == "src/parser.py"


def test_parse_invalid_json_raises(workspace: Path, mock_run: Run) -> None:
    runner = _make_runner(workspace, mock_run)
    with pytest.raises(ValueError, match="Invalid JSON"):
        runner._parse_llm_json("this is not json")


def test_parse_missing_key_raises(workspace: Path, mock_run: Run) -> None:
    runner = _make_runner(workspace, mock_run)
    with pytest.raises(ValueError, match="[Mm]issing"):
        runner._parse_llm_json(
            '{"file": "x.py", "hypothesis": "h", "change_summary": "s"}'
        )
