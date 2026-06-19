"""Tests for GateRunner — uses a mock backend, no real git required."""

from __future__ import annotations

from pathlib import Path

import pytest

from gradex.backends.base import Backend, CommandResult
from gradex.runner.gate import GateRunner

# ---------------------------------------------------------------------------
# Mock backend with call tracking
# ---------------------------------------------------------------------------


class CountingMockBackend(Backend):
    """Backend that returns preset CommandResults in order and counts calls."""

    def __init__(self, results: list[CommandResult]) -> None:
        self._results = results
        self.call_count = 0

    async def create_workspace(self, experiment_id: str) -> Path:  # noqa: D102
        return Path("/fake")

    async def run_command(
        self,
        workspace_path: Path,
        cmd: list[str],
        timeout: int = 120,
        env: dict[str, str] | None = None,
    ) -> CommandResult:  # noqa: D102
        result = self._results[min(self.call_count, len(self._results) - 1)]
        self.call_count += 1
        return result

    async def cleanup_workspace(self, workspace_path: Path) -> None:  # noqa: D102
        pass

    def list_workspaces(self) -> list[Path]:  # noqa: D102
        return []


FAKE = Path("/fake")

_PASS = CommandResult(stdout="", stderr="", exit_code=0, duration_ms=10)
_FAIL = CommandResult(stdout="", stderr="gate failed", exit_code=1, duration_ms=10)
_TIMEOUT = CommandResult(
    stdout="", stderr="", exit_code=-1, duration_ms=1000, timed_out=True
)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_empty_gates_passes() -> None:
    """An empty gate list immediately returns passed=True."""
    runner = GateRunner(CountingMockBackend([]))
    result = await runner.run(FAKE, [])
    assert result.passed is True
    assert result.failures == []


@pytest.mark.anyio
async def test_all_pass() -> None:
    """All gates passing yields passed=True with an empty failures list."""
    backend = CountingMockBackend([_PASS, _PASS])
    runner = GateRunner(backend)
    result = await runner.run(FAKE, ["cmd1", "cmd2"])
    assert result.passed is True
    assert result.failures == []


@pytest.mark.anyio
async def test_first_fails_stops_early() -> None:
    """A failing first gate stops execution; the second gate is never called."""
    backend = CountingMockBackend([_FAIL, _PASS])
    runner = GateRunner(backend)
    result = await runner.run(FAKE, ["cmd1", "cmd2"])
    assert result.passed is False
    assert backend.call_count == 1
    assert len(result.failures) == 1


@pytest.mark.anyio
async def test_gate_timeout() -> None:
    """A timed-out gate is reported as a failure with 'timeout' in the message."""
    backend = CountingMockBackend([_TIMEOUT])
    runner = GateRunner(backend)
    result = await runner.run(FAKE, ["slow-cmd"])
    assert result.passed is False
    assert len(result.failures) == 1
    assert "timeout" in result.failures[0].lower()


@pytest.mark.anyio
async def test_failure_message_truncated() -> None:
    """Stderr is truncated to 500 chars; the total failure entry is ≤ 520 chars."""
    long_stderr = "x" * 1000
    fail_result = CommandResult(
        stdout="", stderr=long_stderr, exit_code=1, duration_ms=10
    )
    backend = CountingMockBackend([fail_result])
    runner = GateRunner(backend)
    result = await runner.run(FAKE, ["cmd"])
    assert result.passed is False
    assert len(result.failures) == 1
    # "<cmd>: " prefix (6 chars) + 500 chars of stderr = 506, well within 520
    assert len(result.failures[0]) <= 520
