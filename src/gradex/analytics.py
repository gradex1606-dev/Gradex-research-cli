"""Analytics and summary computation for Gradex runs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from gradex.config import estimate_llm_cost_usd, load_llm_config
from gradex.repository import ExperimentRepository, RunRepository


@dataclass
class ExperimentBreakdown:
    """Counts of experiments by status within a run."""

    total: int
    passed: int
    rejected: int  # gate failed
    failed: int  # crash / timeout / parse error
    pending: int
    running: int

    @property
    def pass_rate(self) -> float:
        """Percentage of completed experiments that passed."""
        completed = self.passed + self.rejected + self.failed
        if completed == 0:
            return 0.0
        return round((self.passed / completed) * 100, 1)


@dataclass
class RunSummary:
    """High-level summary for a single optimization run."""

    run_id: str
    run_id_short: str  # first 8 chars
    benchmark_cmd: str
    metric_direction: str
    baseline_score: float
    best_score: float | None
    improvement_pct: float | None  # None if no improvement yet
    improvement_abs: float | None  # absolute delta
    breakdown: ExperimentBreakdown
    duration_seconds: float  # from run created_at to last experiment created_at
    avg_experiment_duration_ms: float
    rounds_estimated: int  # total // 3 as a reasonable estimate
    created_at: datetime
    gate_cmds: list[str]
    primary_language: str
    total_input_tokens: int
    total_output_tokens: int
    llm_call_count: int
    estimated_cost_usd: float
    cost_model_label: str


@dataclass
class ScorePoint:
    """A single data point in the score-over-time series."""

    experiment_id: str
    experiment_id_short: str
    score: float
    created_at: datetime
    delta_from_baseline: float
    delta_from_previous: float | None


class RunAnalytics:
    """Query and compute analytics for Gradex runs."""

    def __init__(self) -> None:
        self._run_repo = RunRepository()
        self._exp_repo = ExperimentRepository()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_run_summary(self, run_id: str) -> RunSummary:
        """Compute full summary for a run.

        Raises KeyError if no run with *run_id* exists.
        """
        run = self._run_repo.get(run_id)
        experiments = self._exp_repo.list_by_run(run_id)

        passed = [e for e in experiments if e.status == "passed"]
        rejected = [e for e in experiments if e.status == "rejected"]
        failed = [e for e in experiments if e.status == "failed"]
        pending = [e for e in experiments if e.status == "pending"]
        running = [e for e in experiments if e.status == "running"]

        breakdown = ExperimentBreakdown(
            total=len(experiments),
            passed=len(passed),
            rejected=len(rejected),
            failed=len(failed),
            pending=len(pending),
            running=len(running),
        )

        best_exp = self._exp_repo.get_best(run_id, run.metric_direction)
        best_score: float | None = None
        if best_exp is not None and best_exp.score is not None:
            best_score = best_exp.score

        improvement_pct, improvement_abs = self._compute_improvement(
            run.baseline_score, best_score, run.metric_direction
        )

        # Duration: time from run creation to last experiment creation
        if experiments:
            last_created = max(e.created_at for e in experiments)
            duration_seconds = (last_created - run.created_at).total_seconds()
        else:
            duration_seconds = 0.0

        total = len(experiments)
        rounds_estimated = max(1, total // 3)

        total_in = sum(e.input_tokens for e in experiments)
        total_out = sum(e.output_tokens for e in experiments)
        llm_calls = sum(
            1 for e in experiments if e.input_tokens > 0 or e.output_tokens > 0
        )
        provider = load_llm_config().provider
        cost_model = next(
            (e.llm_model for e in experiments if e.llm_model),
            load_llm_config().effective_model(),
        )
        estimated_cost = sum(
            estimate_llm_cost_usd(provider, e.llm_model or cost_model, e.input_tokens, e.output_tokens)
            for e in experiments
            if e.input_tokens or e.output_tokens
        )
        if estimated_cost == 0.0 and (total_in or total_out):
            estimated_cost = estimate_llm_cost_usd(
                provider, cost_model, total_in, total_out
            )

        return RunSummary(
            run_id=run.id,
            run_id_short=run.id[:8],
            benchmark_cmd=run.benchmark_cmd,
            metric_direction=run.metric_direction,
            baseline_score=run.baseline_score,
            best_score=best_score,
            improvement_pct=improvement_pct,
            improvement_abs=improvement_abs,
            breakdown=breakdown,
            duration_seconds=duration_seconds,
            avg_experiment_duration_ms=0.0,
            rounds_estimated=rounds_estimated,
            created_at=run.created_at,
            gate_cmds=run.get_gate_cmds(),
            primary_language=getattr(run, "primary_language", "python"),
            total_input_tokens=total_in,
            total_output_tokens=total_out,
            llm_call_count=llm_calls,
            estimated_cost_usd=estimated_cost,
            cost_model_label=f"{provider} / {cost_model}",
        )

    def get_score_over_time(self, run_id: str) -> list[ScorePoint]:
        """Return passed experiments sorted by created_at ascending.

        Each point carries ``delta_from_baseline`` and ``delta_from_previous``.
        The first point has ``delta_from_previous=None``.
        """
        run = self._run_repo.get(run_id)
        experiments = self._exp_repo.list_by_run(run_id)

        passed = sorted(
            [e for e in experiments if e.status == "passed" and e.score is not None],
            key=lambda e: e.created_at,
        )

        points: list[ScorePoint] = []
        prev_score: float | None = None

        for exp in passed:
            if exp.score is None:
                continue
            score: float = exp.score
            delta_from_baseline = score - run.baseline_score
            delta_from_previous = (
                (score - prev_score) if prev_score is not None else None
            )
            points.append(
                ScorePoint(
                    experiment_id=exp.id,
                    experiment_id_short=exp.id[:8],
                    score=score,
                    created_at=exp.created_at,
                    delta_from_baseline=delta_from_baseline,
                    delta_from_previous=delta_from_previous,
                )
            )
            prev_score = score

        return points

    def get_all_runs(self, limit: int = 20) -> list[RunSummary]:
        """Return summaries for the most recent *limit* runs, newest first."""
        runs = self._run_repo.list_all(limit=limit)
        return [self.get_run_summary(run.id) for run in runs]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _compute_improvement(
        self,
        baseline: float,
        best: float | None,
        direction: str,
    ) -> tuple[float | None, float | None]:
        """Return (improvement_pct, improvement_abs).

        Positive values always mean an improvement.
        For direction="lower": improvement = baseline - best (positive = got lower).
        For direction="higher": improvement = best - baseline (positive = got higher).
        """
        if best is None:
            return None, None
        if direction == "lower":
            abs_delta = baseline - best
        else:
            abs_delta = best - baseline
        pct = round((abs(abs_delta) / max(abs(baseline), 1e-9)) * 100, 1)
        if abs_delta < 0:
            pct = -pct
        return pct, round(abs_delta, 4)
