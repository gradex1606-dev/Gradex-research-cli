"""Repository classes for Run and Experiment persistence."""

from __future__ import annotations

import uuid

from sqlalchemy import Engine, desc
from sqlmodel import Session, col, select

from gradex.state import Experiment, Run, get_engine


class ExperimentRepository:
    """Data-access layer for :class:`~evo.state.Experiment` records.

    Each method opens its own :class:`~sqlmodel.Session` and closes it before
    returning, so callers never share a session across calls.
    """

    def __init__(self) -> None:
        self._engine: Engine = get_engine()

    def create(
        self,
        run_id: str,
        parent_id: str | None,
        branch: str,
        experiment_id: str | None = None,
    ) -> Experiment:
        """Insert a new experiment in ``"pending"`` status and return it.

        Args:
            run_id:    FK to the owning :class:`~evo.state.Run`.
            parent_id: ID of the parent experiment, or ``None`` for a root.
            branch:    Git branch name for this experiment.
            experiment_id: Optional fixed ID (orchestrator-assigned). Auto-generated if omitted.
        """
        with Session(self._engine) as session:
            exp = Experiment(
                id=experiment_id if experiment_id is not None else str(uuid.uuid4()),
                run_id=run_id,
                parent_id=parent_id,
                branch=branch,
            )
            session.add(exp)
            session.commit()
            session.refresh(exp)
            return exp

    def update_score(
        self,
        id: str,
        score: float,
        gate_passed: bool,
        status: str,
    ) -> Experiment:
        """Update *score*, *gate_passed*, and *status* on an existing experiment.

        Args:
            id:          Primary key of the experiment to update.
            score:       Benchmark score achieved.
            gate_passed: Whether all gate checks passed.
            status:      New status string (e.g. ``"passed"`` or ``"failed"``).

        Raises:
            KeyError: If no experiment with *id* exists.
        """
        with Session(self._engine) as session:
            result = session.exec(select(Experiment).where(Experiment.id == id))
            exp = result.one_or_none()
            if exp is None:
                raise KeyError(f"Experiment {id!r} not found")
            exp.score = score
            exp.gate_passed = gate_passed
            exp.status = status
            session.add(exp)
            session.commit()
            session.refresh(exp)
            return exp

    def update_traces_path(self, id: str, traces_path: str) -> Experiment:
        """Set the relative trace file path for an experiment."""
        with Session(self._engine) as session:
            result = session.exec(select(Experiment).where(Experiment.id == id))
            exp = result.one_or_none()
            if exp is None:
                raise KeyError(f"Experiment {id!r} not found")
            exp.traces_path = traces_path
            session.add(exp)
            session.commit()
            session.refresh(exp)
            return exp

    def update_llm_usage(
        self,
        id: str,
        input_tokens: int,
        output_tokens: int,
        llm_model: str,
    ) -> Experiment:
        """Persist LLM token usage for an experiment."""
        with Session(self._engine) as session:
            result = session.exec(select(Experiment).where(Experiment.id == id))
            exp = result.one_or_none()
            if exp is None:
                raise KeyError(f"Experiment {id!r} not found")
            exp.input_tokens = input_tokens
            exp.output_tokens = output_tokens
            exp.llm_model = llm_model
            session.add(exp)
            session.commit()
            session.refresh(exp)
            return exp

    def resolve_id(self, prefix_or_full: str, run_id: str | None = None) -> str | None:
        """Resolve a full or 8-char experiment ID prefix to a unique experiment ID."""
        needle = prefix_or_full.strip()
        if not needle:
            return None
        with Session(self._engine) as session:
            if run_id:
                results = session.exec(
                    select(Experiment).where(Experiment.run_id == run_id)
                )
                candidates = list(results.all())
            else:
                results = session.exec(select(Experiment))
                candidates = list(results.all())
        exact = [e for e in candidates if e.id == needle]
        if len(exact) == 1:
            return exact[0].id
        prefix_matches = [e for e in candidates if e.id.startswith(needle)]
        if len(prefix_matches) == 1:
            return prefix_matches[0].id
        if len(needle) >= 8:
            short = needle[:8]
            short_matches = [e for e in candidates if e.id.startswith(short)]
            if len(short_matches) == 1:
                return short_matches[0].id
        return None

    def get(self, id: str) -> Experiment:
        """Return the experiment with the given *id*.

        Raises:
            KeyError: If no experiment with *id* exists.
        """
        with Session(self._engine) as session:
            result = session.exec(select(Experiment).where(Experiment.id == id))
            exp = result.one_or_none()
            if exp is None:
                raise KeyError(f"Experiment {id!r} not found")
            return exp

    def list_by_run(self, run_id: str) -> list[Experiment]:
        """Return all experiments belonging to *run_id*, in insertion order."""
        with Session(self._engine) as session:
            results = session.exec(
                select(Experiment).where(Experiment.run_id == run_id)
            )
            return list(results.all())

    def get_best(self, run_id: str, metric_direction: str) -> Experiment | None:
        """Return the best *passed* experiment for *run_id*.

        Args:
            run_id:           FK of the owning run.
            metric_direction: ``"higher"`` selects the max score;
                              ``"lower"`` selects the min score.

        Only experiments with ``status="passed"`` are considered.
        Returns ``None`` if no passed experiments exist.
        """
        with Session(self._engine) as session:
            results = session.exec(
                select(Experiment).where(
                    Experiment.run_id == run_id,
                    Experiment.status == "passed",
                )
            )
            candidates = list(results.all())

        if not candidates:
            return None
        if metric_direction == "higher":
            return max(
                candidates,
                key=lambda e: e.score if e.score is not None else float("-inf"),
            )
        return min(
            candidates,
            key=lambda e: e.score if e.score is not None else float("inf"),
        )


class RunRepository:
    """Data-access layer for :class:`~evo.state.Run` records."""

    def __init__(self) -> None:
        self._engine: Engine = get_engine()

    def create(
        self,
        benchmark_cmd: str,
        metric_direction: str,
        gate_cmds: list[str],
        baseline_score: float,
        primary_language: str = "python",
    ) -> Run:
        """Insert a new run and return it.

        Args:
            benchmark_cmd:    Shell command used to measure the benchmark score.
            metric_direction: ``"higher"`` or ``"lower"``.
            gate_cmds:        List of gate-check shell commands.
            baseline_score:   The reference score to beat.
        """
        with Session(self._engine) as session:
            run = Run(
                benchmark_cmd=benchmark_cmd,
                metric_direction=metric_direction,
                baseline_score=baseline_score,
                primary_language=primary_language,
            )
            run.set_gate_cmds(gate_cmds)
            session.add(run)
            session.commit()
            session.refresh(run)
            return run

    def get(self, id: str) -> Run:
        """Return the run with *id*.

        Raises:
            KeyError: If no run with *id* exists.
        """
        with Session(self._engine) as session:
            result = session.exec(select(Run).where(Run.id == id))
            run = result.one_or_none()
            if run is None:
                raise KeyError(f"Run {id!r} not found")
            return run

    def get_latest(self) -> Run | None:
        """Return the most recently created run, or ``None`` if none exist."""
        with Session(self._engine) as session:
            result = session.exec(select(Run).order_by(desc(col(Run.created_at))))
            return result.first()

    def list_all(self, limit: int = 20) -> list[Run]:
        """Return the most recent *limit* runs ordered by created_at descending."""
        with Session(self._engine) as session:
            result = session.exec(
                select(Run).order_by(desc(col(Run.created_at))).limit(limit)
            )
            return list(result.all())

    def update_baseline_experiment(self, run_id: str, experiment_id: str) -> Run:
        """Set *experiment_id* as the baseline for *run_id* and return the run.

        Raises:
            KeyError: If no run with *run_id* exists.
        """
        with Session(self._engine) as session:
            result = session.exec(select(Run).where(Run.id == run_id))
            run = result.one_or_none()
            if run is None:
                raise KeyError(f"Run {run_id!r} not found")
            run.baseline_experiment_id = experiment_id
            session.add(run)
            session.commit()
            session.refresh(run)
            return run
