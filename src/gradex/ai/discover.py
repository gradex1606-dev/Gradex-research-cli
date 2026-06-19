"""Discover skill: analyse a repo and set up a baseline optimization run."""

from __future__ import annotations

import json
import re
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import jinja2

from gradex.ai.client import LLMClient
from gradex.backends.base import Backend

PROMPTS_DIR = Path(__file__).parent / "prompts"

# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class DiscoverResult:
    """Everything the discover flow found and set up."""

    optimization_target: str
    metric: str
    metric_direction: Literal["higher", "lower"]
    benchmark_script: str
    benchmark_path: Path
    gate_cmds: list[str]
    baseline_score: float
    run_id: str
    notes: str


# ---------------------------------------------------------------------------
# Skill
# ---------------------------------------------------------------------------


class DiscoverSkill:
    """Analyse a repository, design a benchmark, and establish a baseline score.

    Steps performed by :meth:`run`:

    1. Scan the repo to build a context string.
    2. Ask the LLM to pick an optimisation target and metric.
    3. Ask the LLM to write a Python benchmark script; save it.
    4. Detect existing test files.
    5. Ask the LLM to identify gate commands.
    6. Run the benchmark once to capture the baseline score.
    7. Create a :class:`~evo.state.Run` in the database.
    """

    def __init__(self, client: LLMClient, backend: Backend) -> None:
        self._client = client
        self._backend = backend

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def run(
        self,
        repo_root: Path,
        hint: str = "",
    ) -> DiscoverResult:
        """Run the full discover flow for *repo_root*.

        Args:
            repo_root: Root directory of the repository to analyse.
            hint:      Optional user hint, e.g. "make the parser faster".

        Returns a :class:`DiscoverResult` with all artefacts populated.
        """
        # 1 — Repo context
        repo_context = self.scan_repo(repo_root)
        test_files = self.detect_test_files(repo_root)

        # 2 — Target + metric
        analysis_system = (PROMPTS_DIR / "repo_analysis.md").read_text(encoding="utf-8")
        analysis_user = repo_context
        if hint:
            analysis_user += f"\n\nUser hint: {hint}"
        resp1 = await self._client.complete(analysis_system, analysis_user)
        optimization_target = self._parse_xml_tag(resp1.text, "optimization_target")
        metric = self._parse_xml_tag(resp1.text, "metric")
        direction = self._infer_direction(metric)

        # 3 — Benchmark script
        bench_system = jinja2.Template(
            (PROMPTS_DIR / "benchmark_design.md").read_text(encoding="utf-8")
        ).render(
            target=optimization_target,
            metric=metric,
            repo_context=repo_context,
        )
        resp2 = await self._client.complete(
            bench_system, "Write the benchmark script now."
        )
        benchmark_script = self._parse_xml_tag(resp2.text, "benchmark_script")
        notes = ""
        try:
            notes = self._parse_xml_tag(resp2.text, "notes")
        except ValueError:
            pass

        # Write benchmark to disk
        evo_dir = repo_root / ".gradex"
        evo_dir.mkdir(parents=True, exist_ok=True)
        benchmark_path = evo_dir / "benchmark.py"
        benchmark_path.write_text(benchmark_script, encoding="utf-8")

        # 4 + 5 — Gate commands
        gate_system = jinja2.Template(
            (PROMPTS_DIR / "gate_design.md").read_text(encoding="utf-8")
        ).render(
            target=optimization_target,
            test_files=test_files,
        )
        resp3 = await self._client.complete(gate_system, "Identify the gate commands.")
        gate_cmds_raw = self._parse_xml_tag(resp3.text, "gate_cmds")
        gate_cmds: list[str] = json.loads(gate_cmds_raw)
        gate_cmds = self._normalize_gate_cmds(gate_cmds, repo_root, test_files)

        # 6 — Baseline
        baseline_score = await self._run_baseline(repo_root, benchmark_path)

        # 7 — Persist Run
        from gradex.repository import RunRepository

        run = RunRepository().create(
            benchmark_cmd="python .gradex/benchmark.py",
            metric_direction=direction,
            gate_cmds=gate_cmds,
            baseline_score=baseline_score,
        )

        return DiscoverResult(
            optimization_target=optimization_target,
            metric=metric,
            metric_direction=direction,
            benchmark_script=benchmark_script,
            benchmark_path=benchmark_path,
            gate_cmds=gate_cmds,
            baseline_score=baseline_score,
            run_id=run.id,
            notes=notes,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def scan_repo(self, repo_root: Path) -> str:
        """Return a compact text summary of *repo_root* for LLM context.

        Skips ``.git``, ``.evo``, ``__pycache__``, ``node_modules``,
        ``.venv``, and ``dist``.  Output is capped at 3 000 characters.
        """
        _SKIP = {".git", ".gradex", "__pycache__", "node_modules", ".venv", "dist"}
        entries: list[str] = []
        ext_counts: dict[str, int] = {}
        total_size = 0

        def _walk(path: Path, depth: int = 0) -> None:
            if depth > 3 or len(entries) >= 60:
                return
            try:
                children = sorted(path.iterdir())
            except PermissionError:
                return
            for item in children:
                if item.name in _SKIP:
                    continue
                if len(entries) >= 60:
                    entries.append("  ... (truncated)")
                    return
                indent = "  " * depth
                if item.is_dir():
                    entries.append(f"{indent}{item.name}/")
                    _walk(item, depth + 1)
                else:
                    entries.append(f"{indent}{item.name}")
                    ext = item.suffix.lower() or "(no ext)"
                    ext_counts[ext] = ext_counts.get(ext, 0) + 1
                    try:
                        nonlocal total_size
                        total_size += item.stat().st_size
                    except OSError:
                        pass

        _walk(repo_root)
        tree_str = "\n".join(entries)
        ext_str = ", ".join(f"{k}: {v}" for k, v in sorted(ext_counts.items()))
        result = (
            f"Directory tree:\n{tree_str}\n\n"
            f"File types: {ext_str}\n"
            f"Total size: {total_size} bytes"
        )
        return result[:3000]

    def _normalize_gate_cmds(
        self,
        gate_cmds: list[str],
        repo_root: Path,
        test_files: list[str],
    ) -> list[str]:
        """Keep gate commands whose pytest targets exist; fall back to detected tests."""
        valid: list[str] = []
        for cmd in gate_cmds:
            parts = shlex.split(cmd)
            if len(parts) >= 2 and parts[0] == "pytest":
                targets = parts[1:]
                if targets and all((repo_root / target).exists() for target in targets):
                    valid.append(cmd)
            elif parts and parts[0] == "pytest" and not parts[1:]:
                valid.append(cmd)
        if valid:
            return valid
        if test_files:
            return [f"pytest {' '.join(test_files)}"]
        return gate_cmds

    def detect_test_files(self, repo_root: Path) -> list[str]:
        """Return relative paths to test files in *repo_root* (max 20).

        Matches ``test_*.py`` and ``*_test.py`` patterns anywhere under
        *repo_root*.
        """
        seen: set[str] = set()
        results: list[str] = []
        for pattern in ("**/test_*.py", "**/*_test.py"):
            for path in sorted(repo_root.glob(pattern)):
                rel = str(path.relative_to(repo_root))
                if rel not in seen:
                    seen.add(rel)
                    results.append(rel)
        return results[:20]

    def _parse_xml_tag(self, text: str, tag: str) -> str:
        """Extract the content of ``<tag>…</tag>`` from *text*.

        Strips surrounding whitespace.

        Raises:
            ValueError: If the tag is absent.
        """
        match = re.search(f"<{tag}>(.*?)</{tag}>", text, re.DOTALL)
        if not match:
            raise ValueError(f"Tag <{tag}> not found in LLM response")
        return match.group(1).strip()

    def _infer_direction(self, metric: str) -> Literal["higher", "lower"]:
        """Infer optimisation direction from a metric description string.

        ``"lower"`` keywords: lower, minimize, latency, cost, ms, error, loss.
        ``"higher"`` keywords: higher, maximize, accuracy, score, %, throughput.
        Defaults to ``"lower"``.
        """
        lower_m = metric.lower()
        higher_keywords = {"higher", "maximize", "accuracy", "score", "%", "throughput"}
        lower_keywords = {
            "lower",
            "minimize",
            "latency",
            "cost",
            "ms",
            "millisecond",
            "error",
            "loss",
        }
        for kw in higher_keywords:
            if kw in lower_m:
                return "higher"
        for kw in lower_keywords:
            if kw in lower_m:
                return "lower"
        return "lower"

    # ------------------------------------------------------------------
    # Baseline execution
    # ------------------------------------------------------------------

    async def _run_baseline(self, repo_root: Path, benchmark_path: Path) -> float:
        """Execute *benchmark_path* once and parse the resulting score.

        Raises:
            ValueError: If the benchmark times out or yields no parseable score.
        """
        from gradex.runner.benchmark import BenchmarkRunner

        runner = BenchmarkRunner(self._backend, timeout=60)
        result = await runner.run(repo_root, ["python", str(benchmark_path)])
        if result.timed_out:
            raise ValueError("Baseline benchmark timed out")
        if result.score is None:
            detail = result.parse_error or "unknown"
            stderr_hint = ""
            if result.stderr.strip():
                stderr_hint = f"\nBenchmark stderr:\n{result.stderr.strip()[:800]}"
            raise ValueError(
                f"Baseline benchmark returned no parseable score: {detail!r}"
                f"{stderr_hint}\n"
                f"Fix: run `python {benchmark_path}` in your repo and ensure the "
                f"last line of stdout is a single number."
            )
        return result.score
