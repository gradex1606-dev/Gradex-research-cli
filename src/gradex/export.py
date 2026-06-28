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
                    "input_tokens": e.input_tokens,
                    "output_tokens": e.output_tokens,
                    "llm_model": e.llm_model,
                    "created_at": e.created_at.isoformat(),
                }
                for e in experiments
            ],
        }

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return output_path

    def to_html(self, run_id: str, output_path: Path) -> Path:
        """Export a self-contained HTML run report. Returns *output_path*."""
        summary = self._analytics.get_run_summary(run_id)
        score_points = self._analytics.get_score_over_time(run_id)
        experiments = self._exp_repo.list_by_run(run_id)

        best_str = (
            f"{summary.best_score:.4f}" if summary.best_score is not None else "—"
        )
        improvement = (
            f"{summary.improvement_pct:+.1f}%"
            if summary.improvement_pct is not None
            else "—"
        )

        rows = []
        for exp in experiments:
            delta = ""
            if exp.score is not None:
                delta_val = exp.score - summary.baseline_score
                delta = f"{delta_val:+.4f}"
            gate = (
                "pass"
                if exp.gate_passed
                else "fail"
                if exp.gate_passed is False
                else "—"
            )
            rows.append(
                "<tr>"
                f"<td>{exp.id[:8]}</td>"
                f"<td>{exp.status}</td>"
                f"<td>{exp.score if exp.score is not None else '—'}</td>"
                f"<td>{delta}</td>"
                f"<td>{gate}</td>"
                f"<td>{exp.created_at.strftime('%Y-%m-%d %H:%M')}</td>"
                "</tr>"
            )

        score_lines = []
        for i, pt in enumerate(score_points, start=1):
            score_lines.append(
                f"<li>#{i} {pt.experiment_id_short} — {pt.score:.4f}</li>"
            )

        html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>GradeX Run Report — {summary.run_id_short}</title>
  <style>
    body {{ font-family: Inter, system-ui, sans-serif; margin: 0; background: #f8f9ff; color: #0f172a; }}
    .wrap {{ max-width: 920px; margin: 0 auto; padding: 40px 24px 64px; }}
    h1 {{ font-size: 2rem; letter-spacing: -0.04em; margin: 0 0 8px; }}
    .meta {{ color: #64748b; margin-bottom: 28px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px; margin-bottom: 28px; }}
    .card {{ background: #fff; border: 1px solid #e2e8f0; border-radius: 16px; padding: 18px; box-shadow: 0 8px 24px rgba(99,102,241,0.06); }}
    .label {{ font-size: 12px; text-transform: uppercase; letter-spacing: 0.06em; color: #6366f1; font-weight: 700; }}
    .value {{ font-size: 1.5rem; font-weight: 800; margin-top: 6px; }}
    table {{ width: 100%; border-collapse: collapse; background: #fff; border-radius: 16px; overflow: hidden; }}
    th, td {{ padding: 12px 14px; border-bottom: 1px solid #e2e8f0; text-align: left; font-size: 14px; }}
    th {{ background: #eef2ff; color: #4338ca; font-size: 12px; text-transform: uppercase; letter-spacing: 0.05em; }}
    h2 {{ margin: 32px 0 12px; font-size: 1.1rem; }}
    ul {{ margin: 0; padding-left: 20px; color: #475569; }}
    footer {{ margin-top: 40px; color: #94a3b8; font-size: 13px; }}
  </style>
</head>
<body>
  <div class="wrap">
    <h1>GradeX Run Report</h1>
    <p class="meta">Run {summary.run_id_short} · {summary.created_at.strftime('%Y-%m-%d %H:%M')} · {summary.metric_direction} is better</p>
    <div class="grid">
      <div class="card"><div class="label">Baseline</div><div class="value">{summary.baseline_score:.4f}</div></div>
      <div class="card"><div class="label">Best</div><div class="value">{best_str}</div></div>
      <div class="card"><div class="label">Improvement</div><div class="value">{improvement}</div></div>
      <div class="card"><div class="label">Pass rate</div><div class="value">{summary.breakdown.pass_rate}%</div></div>
    </div>
    <p><strong>Benchmark:</strong> <code>{summary.benchmark_cmd}</code></p>
    <p><strong>Gates:</strong> {", ".join(summary.gate_cmds) or "none"}</p>
    <p><strong>LLM usage:</strong> {summary.llm_call_count} calls · {summary.total_input_tokens:,} in / {summary.total_output_tokens:,} out · est. ${summary.estimated_cost_usd:.4f}</p>
    <h2>Score progression (passed)</h2>
    <ul>{"".join(score_lines) if score_lines else "<li>No passed experiments yet</li>"}</ul>
    <h2>Experiments</h2>
    <table>
      <thead><tr><th>ID</th><th>Status</th><th>Score</th><th>Δ baseline</th><th>Gate</th><th>Time</th></tr></thead>
      <tbody>{"".join(rows)}</tbody>
    </table>
    <footer>Generated by GradeX · gradex.dev</footer>
  </div>
</body>
</html>"""

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html, encoding="utf-8")
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
                    "input_tokens",
                    "output_tokens",
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
                        "input_tokens": exp.input_tokens,
                        "output_tokens": exp.output_tokens,
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
            "primary_language": summary.primary_language,
            "total_input_tokens": summary.total_input_tokens,
            "total_output_tokens": summary.total_output_tokens,
            "llm_call_count": summary.llm_call_count,
            "estimated_cost_usd": summary.estimated_cost_usd,
            "cost_model_label": summary.cost_model_label,
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
