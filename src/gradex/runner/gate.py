"""Gate runner: run a sequence of gate commands and report pass/fail."""

from __future__ import annotations

import shlex
import time
from dataclasses import dataclass
from pathlib import Path

from gradex.backends.base import Backend


@dataclass
class GateResult:
    """The outcome of running all gate commands."""

    passed: bool
    failures: list[str]  # one entry per failed gate: "<cmd>: <reason>"
    duration_ms: int


class GateRunner:
    """Runs gate commands sequentially; stops at the first failure.

    Each command string is split via :func:`shlex.split` before being passed
    to the backend.  An empty *gate_cmds* list is treated as an automatic
    pass with zero duration.
    """

    def __init__(self, backend: Backend, timeout: int = 120) -> None:
        self._backend = backend
        self._timeout = timeout

    async def run(
        self,
        workspace_path: Path,
        gate_cmds: list[str],
    ) -> GateResult:
        """Execute each gate command in *workspace_path*, stopping at first failure.

        Args:
            workspace_path: Directory in which commands are executed.
            gate_cmds:      Ordered list of shell-style command strings.

        Returns a :class:`GateResult` with ``passed=True`` only if every
        command exits 0 within *timeout* seconds.
        """
        if not gate_cmds:
            return GateResult(passed=True, failures=[], duration_ms=0)

        start = time.perf_counter()
        failures: list[str] = []

        for cmd_str in gate_cmds:
            cmd = shlex.split(cmd_str)
            result = await self._backend.run_command(
                workspace_path, cmd, timeout=self._timeout
            )
            if result.timed_out:
                failures.append(f"{cmd_str}: timeout")
                break
            if result.exit_code != 0:
                failures.append(f"{cmd_str}: {result.stderr[:500]}")
                break

        duration_ms = int((time.perf_counter() - start) * 1000)
        return GateResult(
            passed=len(failures) == 0,
            failures=failures,
            duration_ms=duration_ms,
        )
