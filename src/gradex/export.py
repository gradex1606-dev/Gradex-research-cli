"""Export run data to JSON or CSV formats."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from gradex.analytics import RunAnalytics, RunSummary
from gradex.repository import ExperimentRepository


class RunExporter:
    """Export run data to JSON or CSV."""

    def __init__(self, analytics: RunAnalytics | None = None) -> None:
        self._analytics = analytics or RunAnalytics()
        self._exp_repo = ExperimentRepository()

    def to_json(self, run_id: str, output_path: Path) -> Path:
        """Export full run data to JSON.

        Structure::

            {
              "summary": { ...RunSummary fields... },
              "score_over_time": [ ...ScorePoint list... ],
              "experiments": [ ...all experiments for this run... ]
            }

        Datetimes are serialized as ISO strings. Returns *output_path*.
        """
        summary = self._analytics.get_run_summary(run_id)
        score_points = self._analytics.get_score_over_time(run_id)
        experiments = self._exp_repo.list_by_run(run_id)

        data: dict[str, Any] = {
            "summary": self._summary_to_dict(summary),
            "score_over_time": [
                {
                    "experiment_id": pt.experiment_id,
                    "experiment_id_short": pt.experiment_id_short,
                    "score": pt.score,
                    "created_at": pt.created_at.isoformat(),
                    "delta_from_baseline": pt.delta_from_baseline,
                    "delta_from_previous": pt.delta_from_previous,
                }
                for pt in score_points
            ],
            "experiments": [
                {
                    "id": e.id,
                    "run_id": e.run_id,
                    "branch": e.branch,
                    "status": e.status,
                    "score": e.score,
                    "gate_passed": e.gate_passed,
                    "created_at": e.created_at.isoformat(),
                }
                for e in experiments
            ],
        }

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return output_path

    def to_csv(self, run_id: str, output_path: Path) -> Path:
        """Export experiments to CSV.

        Columns: id, status, score, gate_passed, delta_from_baseline, created_at.
        Returns *output_path*.
        """
        summary = self._analytics.get_run_summary(run_id)
        experiments = self._exp_repo.list_by_run(run_id)
        baseline = summary.baseline_score

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "id",
                    "status",
                    "score",
                    "gate_passed",
                    "delta_from_baseline",
                    "created_at",
                ],
            )
            writer.writeheader()
            for exp in experiments:
                delta = (exp.score - baseline) if exp.score is not None else ""
                writer.writerow(
                    {
                        "id": exp.id,
                        "status": exp.status,
                        "score": exp.score if exp.score is not None else "",
                        "gate_passed": exp.gate_passed
                        if exp.gate_passed is not None
                        else "",
                        "delta_from_baseline": delta,
                        "created_at": exp.created_at.isoformat(),
                    }
                )
        return output_path

    def _summary_to_dict(self, summary: RunSummary) -> dict[str, Any]:
        """Convert RunSummary to a JSON-serializable dict."""
        return {
            "run_id": summary.run_id,
            "run_id_short": summary.run_id_short,
            "benchmark_cmd": summary.benchmark_cmd,
            "metric_direction": summary.metric_direction,
            "baseline_score": summary.baseline_score,
            "best_score": summary.best_score,
            "improvement_pct": summary.improvement_pct,
            "improvement_abs": summary.improvement_abs,
            "duration_seconds": summary.duration_seconds,
            "avg_experiment_duration_ms": summary.avg_experiment_duration_ms,
            "rounds_estimated": summary.rounds_estimated,
            "created_at": summary.created_at.isoformat(),
            "gate_cmds": summary.gate_cmds,
            "breakdown": {
                "total": summary.breakdown.total,
                "passed": summary.breakdown.passed,
                "rejected": summary.breakdown.rejected,
                "failed": summary.breakdown.failed,
                "pending": summary.breakdown.pending,
                "running": summary.breakdown.running,
                "pass_rate": summary.breakdown.pass_rate,
            },
        }
