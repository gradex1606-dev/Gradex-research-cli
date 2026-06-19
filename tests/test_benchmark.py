"""Tests for BenchmarkRunner — uses a mock backend, no real git required."""

from __future__ import annotations

from pathlib import Path

import pytest

from gradex.backends.base import Backend, CommandResult
from gradex.runner.benchmark import BenchmarkRunner

# ---------------------------------------------------------------------------
# Mock backend
# ---------------------------------------------------------------------------


class MockBackend(Backend):
    """Backend that returns a preset CommandResult for every run_command call."""

    def __init__(
        self,
        stdout: str = "",
        exit_code: int = 0,
        timed_out: bool = False,
    ) -> None:
        self.stdout = stdout
        self.exit_code = exit_code
        self.timed_out = timed_out

    async def create_workspace(self, experiment_id: str) -> Path:  # noqa: D102
        return Path("/fake")

    async def run_command(
        self,
        workspace_path: Path,
        cmd: list[str],
        timeout: int = 120,
        env: dict[str, str] | None = None,
    ) -> CommandResult:  # noqa: D102
        return CommandResult(
            stdout=self.stdout,
            stderr="",
            exit_code=self.exit_code,
            duration_ms=50,
            timed_out=self.timed_out,
        )

    async def cleanup_workspace(self, workspace_path: Path) -> None:  # noqa: D102
        pass

    def list_workspaces(self) -> list[Path]:  # noqa: D102
        return []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAKE = Path("/fake")


async def _run(stdout: str, exit_code: int = 0, timed_out: bool = False) -> object:
    runner = BenchmarkRunner(
        MockBackend(stdout=stdout, exit_code=exit_code, timed_out=timed_out)
    )
    return await runner.run(FAKE, ["bench"])


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_parse_exact_float() -> None:
    """A line containing only a float is parsed as the score."""
    result = await BenchmarkRunner(MockBackend(stdout="29.7\n")).run(FAKE, ["bench"])
    assert result.score == pytest.approx(29.7)
    assert result.parse_error is None


@pytest.mark.anyio
async def test_parse_trailing_token() -> None:
    """The last whitespace-separated token is extracted when the full line isn't a float."""
    result = await BenchmarkRunner(MockBackend(stdout="latency: 29.7\n")).run(
        FAKE, ["bench"]
    )
    assert result.score == pytest.approx(29.7)


@pytest.mark.anyio
async def test_parse_integer() -> None:
    """An integer on its own line is coerced to float."""
    result = await BenchmarkRunner(MockBackend(stdout="100\n")).run(FAKE, ["bench"])
    assert result.score == pytest.approx(100.0)


@pytest.mark.anyio
async def test_parse_scientific() -> None:
    """Scientific-notation output is parsed correctly."""
    result = await BenchmarkRunner(MockBackend(stdout="1.2e-3\n")).run(FAKE, ["bench"])
    assert result.score == pytest.approx(0.0012)


@pytest.mark.anyio
async def test_parse_multiline() -> None:
    """Only the last non-empty line is used for parsing."""
    result = await BenchmarkRunner(MockBackend(stdout="warming up\n29.7\n")).run(
        FAKE, ["bench"]
    )
    assert result.score == pytest.approx(29.7)


@pytest.mark.anyio
async def test_parse_failure() -> None:
    """A line with no numeric content yields score=None and a parse_error."""
    result = await BenchmarkRunner(MockBackend(stdout="no numbers here\n")).run(
        FAKE, ["bench"]
    )
    assert result.score is None
    assert result.parse_error is not None
    assert len(result.parse_error) > 0


@pytest.mark.anyio
async def test_parse_empty_stdout() -> None:
    """Empty stdout yields score=None with a descriptive parse_error."""
    result = await BenchmarkRunner(MockBackend(stdout="")).run(FAKE, ["bench"])
    assert result.score is None
    assert result.parse_error is not None


@pytest.mark.anyio
async def test_timeout_propagates() -> None:
    """A timed-out command propagates timed_out=True and score=None."""
    result = await BenchmarkRunner(MockBackend(stdout="", timed_out=True)).run(
        FAKE, ["bench"]
    )
    assert result.timed_out is True
    assert result.score is None


@pytest.mark.anyio
async def test_nonzero_exit_score_still_parsed() -> None:
    """A non-zero exit code does not prevent score parsing from stdout."""
    result = await BenchmarkRunner(MockBackend(stdout="41.2\n", exit_code=1)).run(
        FAKE, ["bench"]
    )
    assert result.score == pytest.approx(41.2)
