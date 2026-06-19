"""Orchestrator: top-level optimization loop coordinating parallel subagents."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from typing import Literal

from gradex.ai.brief import BriefGenerator, ExperimentSummary
from gradex.dashboard.broadcaster import DashboardBroadcaster
from gradex.repository import ExperimentRepository, RunRepository
from gradex.state import Run
from gradex.subagent import SubagentResult, SubagentRunner


@dataclass
class OrchestratorConfig:
    """Tunable knobs for the optimization loop."""

    subagents: int = 3
    budget: int = 5
    stall: int = 3
    round_timeout: int = 600


@dataclass
class OrchestratorResult:
    """Summary of a completed optimization run."""

    run_id: str
    rounds_completed: int
    total_experiments: int
    experiments_passed: int
    baseline_score: float
    best_score: float | None
    improvement_pct: float | None
    stopped_reason: Literal["stall", "budget", "error"]


class Orchestrator:
    """Drives the full multi-round optimization loop.

    Each round spawns :attr:`~OrchestratorConfig.subagents` parallel
    :class:`~evo.subagent.SubagentRunner` tasks, evaluates their results,
    and updates the best-known score.  The loop stops when the stall limit
    is reached, the experiment budget is exhausted, or a round times out.
    """

    def __init__(
        self,
        run: Run,
        subagent_runner: SubagentRunner,
        brief_generator: BriefGenerator,
        broadcaster: DashboardBroadcaster,
        config: OrchestratorConfig,
        exp_repo: ExperimentRepository | None = None,
        run_repo: RunRepository | None = None,
    ) -> None:
        self._run = run
        self._subagent_runner = subagent_runner
        self._brief_generator = brief_generator
        self._broadcaster = broadcaster
        self._config = config
        self._exp_repo = exp_repo if exp_repo is not None else ExperimentRepository()
        self._run_repo = run_repo if run_repo is not None else RunRepository()

    async def run(self) -> OrchestratorResult:
        """Main optimization loop.

        Returns an :class:`OrchestratorResult` summarising all rounds.
        Never raises — exceptions from subagents are handled via
        ``asyncio.gather(return_exceptions=True)``.
        """
        current_best_score: float = self._run.baseline_score
        best_experiment_id: str | None = None
        stall_counter: int = 0
        total_experiments: int = 0
        experiments_passed: int = 0
        round_num: int = 0
        stopped_reason: Literal["stall", "budget", "error"] = "stall"

        while True:
            round_num += 1
            improved_this_round = False

            # Build context from all past experiments in this run
            past_experiments = self._build_past_experiments()

            # Generate one brief per subagent
            gate_cmds = self._run.get_gate_cmds()
            gate_cmd_str = "; ".join(gate_cmds) if gate_cmds else ""
            briefs = [
                self._brief_generator.generate(
                    optimization_target=(
                        "Make parse_payment_ids in parser.py faster "
                        "while keeping pytest test_parser.py passing"
                    ),
                    metric=self._run.benchmark_cmd,
                    metric_direction=self._run.metric_direction,
                    baseline_score=self._run.baseline_score,
                    best_score=current_best_score,
                    benchmark_cmd=self._run.benchmark_cmd,
                    gate_cmd=gate_cmd_str,
                    past_experiments=past_experiments,
                    agent_index=i,
                )
                for i in range(self._config.subagents)
            ]

            # Create experiment IDs upfront so the orchestrator controls them
            experiment_ids = [str(uuid.uuid4()) for _ in range(self._config.subagents)]

            tasks = [
                self._subagent_runner.run(
                    experiment_id=eid,
                    parent_id=best_experiment_id,
                    brief=briefs[i],
                    agent_index=i,
                )
                for i, eid in enumerate(experiment_ids)
            ]

            try:
                raw_results = await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True),
                    timeout=float(self._config.round_timeout),
                )
            except TimeoutError:
                stopped_reason = "error"
                break

            # Evaluate each result
            for raw in raw_results:
                total_experiments += 1

                if isinstance(raw, BaseException):
                    # Subagent raised — count as a failed experiment
                    continue

                result: SubagentResult = raw
                is_improvement = self._is_improvement(result.score, current_best_score)

                status: Literal["passed", "rejected", "failed"]
                if result.score is not None and result.gate_passed and is_improvement:
                    status = "passed"
                    current_best_score = result.score
                    best_experiment_id = result.experiment_id
                    experiments_passed += 1
                    improved_this_round = True
                elif not result.gate_passed:
                    status = "rejected"
                else:
                    status = "failed"

                # Persist result — KeyError means subagent was mocked/skipped DB
                try:
                    self._exp_repo.update_score(
                        result.experiment_id,
                        result.score if result.score is not None else 0.0,
                        result.gate_passed,
                        status,
                    )
                except KeyError:
                    pass

                await self._broadcaster.broadcast(
                    {
                        "type": "experiment_update",
                        "data": {
                            "id": result.experiment_id[:8],
                            "status": status,
                            "score": result.score,
                            "gate_passed": result.gate_passed,
                        },
                    }
                )

            # Round summary
            if improved_this_round:
                stall_counter = 0
                await self._broadcaster.broadcast(
                    {"type": "round_complete", "best_score": current_best_score}
                )
            else:
                stall_counter += 1

            # Stopping conditions
            if stall_counter >= self._config.stall:
                stopped_reason = "stall"
                break
            if total_experiments >= self._config.subagents * self._config.budget:
                stopped_reason = "budget"
                break

        best_score: float | None = (
            current_best_score if best_experiment_id is not None else None
        )
        improvement_pct: float | None = None
        if best_score is not None and self._run.baseline_score != 0.0:
            improvement_pct = (
                abs(best_score - self._run.baseline_score)
                / abs(self._run.baseline_score)
                * 100.0
            )

        return OrchestratorResult(
            run_id=self._run.id,
            rounds_completed=round_num,
            total_experiments=total_experiments,
            experiments_passed=experiments_passed,
            baseline_score=self._run.baseline_score,
            best_score=best_score,
            improvement_pct=improvement_pct,
            stopped_reason=stopped_reason,
        )

    def _is_improvement(self, score: float | None, current_best: float) -> bool:
        """Return ``True`` if *score* is strictly better than *current_best*."""
        if score is None:
            return False
        if self._run.metric_direction == "lower":
            return score < current_best
        return score > current_best

    def _build_past_experiments(self) -> list[ExperimentSummary]:
        """Query all terminal experiments for this run and convert to summaries."""
        result_map: dict[str, str] = {
            "passed": "improved",
            "rejected": "gate_failed",
            "failed": "failed",
        }
        summaries: list[ExperimentSummary] = []
        try:
            for exp in self._exp_repo.list_by_run(self._run.id):
                if exp.status in ("running", "pending"):
                    continue
                mapped = result_map.get(exp.status, "failed")
                reason = f"score={exp.score}" if exp.score is not None else "no score"
                summaries.append(
                    ExperimentSummary(
                        hypothesis="",
                        result=mapped,
                        reason=reason,
                    )
                )
        except Exception:  # noqa: BLE001
            pass
        return summaries
