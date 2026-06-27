"""Benchmark runner: execute a command and parse a numeric score from stdout."""

from __future__ import annotations

import os
import re
import shlex
from dataclasses import dataclass
from pathlib import Path

from gradex.backends.base import Backend, CommandResult
from gradex.runner.cache import BenchmarkCache, get_git_tree_hash

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
    from_cache: bool = False


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

    def __init__(
        self,
        backend: Backend,
        timeout: int = 120,
        cache: BenchmarkCache | None | bool = None,
    ) -> None:
        self._backend = backend
        self._timeout = timeout
        if cache is False:
            self._cache: BenchmarkCache | None = None
        elif cache is None:
            self._cache = BenchmarkCache()
        else:
            self._cache = cache

    def _cmd_key(self, benchmark_cmd: list[str]) -> str:
        return shlex.join(benchmark_cmd)

    async def run(
        self,
        workspace_path: Path,
        benchmark_cmd: list[str],
    ) -> BenchmarkResult:
        """Run *benchmark_cmd* in *workspace_path* and return a :class:`BenchmarkResult`.

        A non-zero exit code does **not** prevent score parsing — some benchmarks
        exit non-zero yet still print a valid score on stdout.

        When a fresh score is computed for an unchanged git tree, the result is
        stored in the benchmark cache (24h TTL).
        """
        cmd_key = self._cmd_key(benchmark_cmd)
        tree_hash = get_git_tree_hash(workspace_path)

        if self._cache is not None:
            cached_score = self._cache.get(cmd_key, tree_hash)
            if cached_score is not None:
                return BenchmarkResult(
                    score=cached_score,
                    stdout="(cached)",
                    stderr="",
                    duration_ms=0,
                    timed_out=False,
                    parse_error=None,
                    from_cache=True,
                )
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
            result = _make_ok(score, raw)
            if self._cache is not None and tree_hash:
                self._cache.put(cmd_key, tree_hash, score)
            return result

        # Strategy 2 — last whitespace token
        tokens = last.split()
        if tokens:
            score = _try_float(tokens[-1])
            if score is not None:
                result = _make_ok(score, raw)
                if self._cache is not None and tree_hash:
                    self._cache.put(cmd_key, tree_hash, score)
                return result

        # Strategy 3 — first float-like substring via regex
        m = _FLOAT_RE.search(last)
        if m:
            score = _try_float(m.group())
            if score is not None:
                result = _make_ok(score, raw)
                if self._cache is not None and tree_hash:
                    self._cache.put(cmd_key, tree_hash, score)
                return result

        return BenchmarkResult(
            score=None,
            stdout=raw.stdout,
            stderr=raw.stderr,
            duration_ms=raw.duration_ms,
            timed_out=False,
            parse_error=last,
        )
