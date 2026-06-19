"""Benchmark runner: execute a command and parse a numeric score from stdout."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from gradex.backends.base import Backend, CommandResult

# Matches integers, decimals, and scientific-notation floats (e.g. 1.2e-3).
_FLOAT_RE = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")


@dataclass
class BenchmarkResult:
    """The outcome of a benchmark run, including the extracted numeric score."""

    score: float | None
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool
    parse_error: str | None = None


def _try_float(value: str) -> float | None:
    """Return ``float(value)`` or ``None`` if conversion fails."""
    try:
        return float(value)
    except ValueError:
        return None


def _make_ok(score: float, raw: CommandResult) -> BenchmarkResult:
    return BenchmarkResult(
        score=score,
        stdout=raw.stdout,
        stderr=raw.stderr,
        duration_ms=raw.duration_ms,
        timed_out=False,
        parse_error=None,
    )


class BenchmarkRunner:
    """Executes a benchmark command and extracts a float score from its output.

    Parsing is attempted against the **last non-empty line** of stdout using
    three strategies in order:

    1. The entire trimmed line is a float.
    2. The last whitespace-separated token on the line is a float.
    3. The first float-like token found anywhere on the line (via regex).

    If none succeed, ``score=None`` and ``parse_error`` is populated.
    The runner never raises — all errors are reflected in the result object.
    """

    def __init__(self, backend: Backend, timeout: int = 120) -> None:
        self._backend = backend
        self._timeout = timeout

    async def run(
        self,
        workspace_path: Path,
        benchmark_cmd: list[str],
    ) -> BenchmarkResult:
        """Run *benchmark_cmd* in *workspace_path* and return a :class:`BenchmarkResult`.

        A non-zero exit code does **not** prevent score parsing — some benchmarks
        exit non-zero yet still print a valid score on stdout.
        """
        run_env = os.environ.copy()
        root = str(workspace_path.resolve())
        sep = ";" if os.name == "nt" else ":"
        existing = run_env.get("PYTHONPATH", "")
        run_env["PYTHONPATH"] = f"{root}{sep}{existing}" if existing else root

        raw = await self._backend.run_command(
            workspace_path,
            benchmark_cmd,
            timeout=self._timeout,
            env=run_env,
        )

        if raw.timed_out:
            return BenchmarkResult(
                score=None,
                stdout=raw.stdout,
                stderr=raw.stderr,
                duration_ms=raw.duration_ms,
                timed_out=True,
                parse_error="Command timed out",
            )

        non_empty = [ln for ln in raw.stdout.splitlines() if ln.strip()]
        if not non_empty:
            return BenchmarkResult(
                score=None,
                stdout=raw.stdout,
                stderr=raw.stderr,
                duration_ms=raw.duration_ms,
                timed_out=False,
                parse_error="No output from benchmark command",
            )

        last = non_empty[-1]

        # Strategy 1 — entire line
        score = _try_float(last.strip())
        if score is not None:
            return _make_ok(score, raw)

        # Strategy 2 — last whitespace token
        tokens = last.split()
        if tokens:
            score = _try_float(tokens[-1])
            if score is not None:
                return _make_ok(score, raw)

        # Strategy 3 — first float-like substring via regex
        m = _FLOAT_RE.search(last)
        if m:
            score = _try_float(m.group())
            if score is not None:
                return _make_ok(score, raw)

        return BenchmarkResult(
            score=None,
            stdout=raw.stdout,
            stderr=raw.stderr,
            duration_ms=raw.duration_ms,
            timed_out=False,
            parse_error=last,
        )
