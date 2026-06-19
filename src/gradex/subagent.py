"""Subagent runner: execute one experiment in an isolated worktree."""

from __future__ import annotations

import json
import re
import shlex
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from sqlmodel import Session, select

from gradex.ai.client import LLMClient
from gradex.backends.base import Backend
from gradex.dashboard.broadcaster import DashboardBroadcaster
from gradex.repository import ExperimentRepository
from gradex.runner.benchmark import BenchmarkRunner
from gradex.runner.gate import GateRunner
from gradex.state import Experiment, Run, get_engine
from gradex.traces import TraceWriter, trace_path_for

_SYSTEM_PROMPT = (
    "You are a code optimization agent. "
    "You must preserve all existing behavior — every pytest gate must pass. "
    "Only change parser.py. Prefer simple, correct Python over clever hacks. "
    "Read test_parser.py carefully: your implementation must satisfy every assertion."
)

_SOURCE_FILES = ("parser.py", "test_parser.py")

_JSON_INSTRUCTION = (
    "Respond ONLY with a JSON object:\n"
    "{\n"
    '  "file": "relative/path/to/file.py",\n'
    '  "new_content": "<complete new file content>",\n'
    '  "hypothesis": "one sentence",\n'
    '  "change_summary": "what you changed"\n'
    "}\n"
    "No markdown fences. No explanation. JSON only."
)

_FENCE_RE = re.compile(r"```(?:json)?\s*\n?(.*?)\n?```", re.DOTALL)


@dataclass
class SubagentResult:
    """The outcome of a single subagent experiment run."""

    experiment_id: str
    score: float | None
    gate_passed: bool
    hypothesis: str
    change_summary: str
    error: str | None
    duration_ms: int


class SubagentRunner:
    """Runs one experiment in an isolated worktree.

    V1 Protocol: makes a single LLM call, applies the suggested change,
    then runs the benchmark and gate.  Never raises — all errors are
    captured in :attr:`SubagentResult.error`.
    """

    def __init__(
        self,
        backend: Backend,
        benchmark_runner: BenchmarkRunner,
        gate_runner: GateRunner,
        llm_client: LLMClient,
        run: Run,
    ) -> None:
        self._backend = backend
        self._benchmark_runner = benchmark_runner
        self._gate_runner = gate_runner
        self._llm_client = llm_client
        self._run = run
        self._exp_repo = ExperimentRepository()

    async def run(
        self,
        experiment_id: str,
        parent_id: str | None,
        brief: str,
        agent_index: int,
    ) -> SubagentResult:
        """Full experiment lifecycle.

        Steps:
        1. Create experiment record in DB.
        2. Mark status ``"running"`` and broadcast.
        3. Create workspace via backend.
        4. Write ``BRIEF.md``.
        5. Make one LLM call requesting a JSON code change.
        6. Parse the JSON, write the modified file.
        7. Run the benchmark command.
        8. Run the gate commands.
        9. Write trace entries.
        10. Clean up workspace.
        11. Return :class:`SubagentResult`.

        On any exception: clean up workspace, mark experiment ``"failed"``,
        return a result with ``error`` populated.
        """
        start_ns = time.perf_counter_ns()
        workspace: Path | None = None

        try:
            # 1. Create experiment in DB (use orchestrator-assigned ID)
            branch = f"gradex/{experiment_id[:8]}"
            self._exp_repo.create(
                self._run.id, parent_id, branch, experiment_id=experiment_id
            )

            # 2. Mark running and broadcast
            self._set_status(experiment_id, "running")
            await DashboardBroadcaster.get().broadcast(
                {
                    "type": "experiment_update",
                    "data": {"id": experiment_id[:8], "status": "running"},
                }
            )

            # 3. Create workspace
            workspace = await self._backend.create_workspace(experiment_id)
            self._prepare_workspace(workspace)

            # 4. Write BRIEF.md
            (workspace / "BRIEF.md").write_text(brief, encoding="utf-8")

            # 5. Make one LLM call (include source + tests so gates pass)
            source_ctx = self._source_context(workspace)
            user_msg = f"{brief}\n\n{source_ctx}\n\n{_JSON_INSTRUCTION}"
            llm_response = await self._llm_client.complete(
                system=_SYSTEM_PROMPT, user=user_msg
            )

            # 6. Parse JSON and write the file
            parsed = self._parse_llm_json(llm_response.text)
            target = workspace / parsed["file"]
            safe_path_check = getattr(self._backend, "_assert_safe_path", None)
            if callable(safe_path_check):
                safe_path_check(target, workspace)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(parsed["new_content"], encoding="utf-8")

            # 7. Run benchmark
            benchmark_result = await self._benchmark_runner.run(
                workspace, shlex.split(self._run.benchmark_cmd)
            )

            # 8. Run gate
            gate_result = await self._gate_runner.run(
                workspace, self._run.get_gate_cmds()
            )

            # 9. Write traces
            tracer = TraceWriter(trace_path_for(experiment_id))
            tracer.write(
                "info",
                "started",
                {"experiment_id": experiment_id, "agent_index": agent_index},
            )
            tracer.write(
                "info",
                "llm_response",
                {
                    "input_tokens": llm_response.input_tokens,
                    "output_tokens": llm_response.output_tokens,
                },
            )
            tracer.write(
                "info",
                "benchmark",
                {
                    "score": benchmark_result.score,
                    "timed_out": benchmark_result.timed_out,
                },
            )
            tracer.write(
                "info",
                "gate",
                {
                    "passed": gate_result.passed,
                    "failures": gate_result.failures,
                },
            )

            # 10. Clean up
            await self._backend.cleanup_workspace(workspace)

            duration_ms = (time.perf_counter_ns() - start_ns) // 1_000_000

            error: str | None = None
            if benchmark_result.timed_out:
                error = "benchmark timed out"

            return SubagentResult(
                experiment_id=experiment_id,
                score=benchmark_result.score,
                gate_passed=gate_result.passed,
                hypothesis=parsed["hypothesis"],
                change_summary=parsed["change_summary"],
                error=error,
                duration_ms=int(duration_ms),
            )

        except Exception as exc:  # noqa: BLE001
            if workspace is not None:
                try:
                    await self._backend.cleanup_workspace(workspace)
                except Exception:  # noqa: BLE001
                    pass
            self._set_status(experiment_id, "failed")
            duration_ms = (time.perf_counter_ns() - start_ns) // 1_000_000
            return SubagentResult(
                experiment_id=experiment_id,
                score=None,
                gate_passed=False,
                hypothesis="",
                change_summary="",
                error=str(exc),
                duration_ms=int(duration_ms),
            )

    @staticmethod
    def _source_context(workspace: Path) -> str:
        """Include key source files in the LLM prompt so gates are easier to pass."""
        sections: list[str] = []
        for name in _SOURCE_FILES:
            path = workspace / name
            if not path.is_file():
                continue
            sections.append(
                f"## Current `{name}`\n```python\n{path.read_text(encoding='utf-8')}\n```"
            )
        if not sections:
            return ""
        return "## Source files (read before editing)\n\n" + "\n\n".join(sections)

    def _prepare_workspace(self, workspace: Path) -> None:
        """Copy gitignored demo assets (benchmark) into the isolated worktree."""
        repo_root = getattr(self._backend, "_repo_root", None)
        gradex_dir = workspace / ".gradex"
        benchmark_dest = gradex_dir / "benchmark.py"

        if repo_root is not None:
            src = Path(repo_root) / ".gradex" / "benchmark.py"
            if src.is_file():
                gradex_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, benchmark_dest)
                return

        demo_benchmark = workspace / "benchmark_demo.py"
        if demo_benchmark.is_file():
            gradex_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(demo_benchmark, benchmark_dest)

    def _parse_llm_json(self, text: str) -> dict[str, str]:
        """Parse JSON from an LLM response, stripping markdown fences if present.

        Args:
            text: Raw LLM output, potentially wrapped in \\`\\`\\`json ... \\`\\`\\`.

        Returns:
            Dict with keys ``file``, ``new_content``, ``hypothesis``,
            ``change_summary``.

        Raises:
            ValueError: If the JSON is invalid or a required key is missing.
        """
        stripped = text.strip()
        m = _FENCE_RE.search(stripped)
        if m:
            stripped = m.group(1).strip()

        try:
            data: dict[str, object] = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON from LLM: {exc}") from exc

        required = {"file", "new_content", "hypothesis", "change_summary"}
        missing = required - data.keys()
        if missing:
            raise ValueError(f"LLM JSON missing keys: {missing}")

        return {k: str(data[k]) for k in required}

    def _set_status(self, experiment_id: str, status: str) -> None:
        """Best-effort synchronous status update directly via SQLModel session."""
        try:
            with Session(get_engine()) as session:
                stmt = select(Experiment).where(Experiment.id == experiment_id)
                exp = session.exec(stmt).one_or_none()
                if exp is not None:
                    exp.status = status
                    session.add(exp)
                    session.commit()
        except Exception:  # noqa: BLE001
            pass
