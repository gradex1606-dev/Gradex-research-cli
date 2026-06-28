"""FastAPI application and port-selection utility for the gradex dashboard."""

from __future__ import annotations

import socket
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.responses import Response

from gradex.dashboard.broadcaster import DashboardBroadcaster
from gradex.repository import ExperimentRepository, RunRepository
from gradex.traces import TraceReader, trace_path_for

TEMPLATES_DIR = Path(__file__).parent / "templates"


def _resolve_experiment_or_404(experiment_id: str) -> tuple[str, Any]:
    """Resolve experiment ID prefix and return (full_id, Experiment)."""
    exp_repo = ExperimentRepository()
    resolved = exp_repo.resolve_id(experiment_id)
    if resolved is None:
        raise HTTPException(status_code=404, detail="experiment not found")
    try:
        exp = exp_repo.get(resolved)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="experiment not found") from exc
    return resolved, exp


def _experiment_detail_payload(experiment_id: str) -> dict[str, Any]:
    """Build JSON payload for experiment detail including traces."""
    _, exp = _resolve_experiment_or_404(experiment_id)
    run = RunRepository().get(exp.run_id)
    trace_path = trace_path_for(exp.id)
    traces = TraceReader(trace_path).read_all()
    return {
        "experiment": {
            "id": exp.id,
            "id_short": exp.id[:8],
            "run_id": exp.run_id,
            "parent_id": exp.parent_id,
            "branch": exp.branch,
            "score": exp.score,
            "gate_passed": exp.gate_passed,
            "status": exp.status,
            "traces_path": exp.traces_path,
            "input_tokens": exp.input_tokens,
            "output_tokens": exp.output_tokens,
            "llm_model": exp.llm_model,
            "created_at": exp.created_at.isoformat(),
        },
        "run": {
            "id": run.id,
            "benchmark_cmd": run.benchmark_cmd,
            "metric_direction": run.metric_direction,
            "baseline_score": run.baseline_score,
            "gate_cmds": run.get_gate_cmds(),
            "primary_language": getattr(run, "primary_language", "python"),
        },
        "traces": traces,
    }


def find_free_port(start: int = 8080, attempts: int = 20) -> int:
    """Return the first free TCP port in ``[start, start + attempts)``.

    Args:
        start:    First port number to try.
        attempts: How many consecutive ports to probe before giving up.

    Raises:
        RuntimeError: If no free port is found within the range.
    """
    for port in range(start, start + attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"No free port found in range {start}-{start + attempts}")


def create_app() -> FastAPI:
    """Construct and return the gradex dashboard FastAPI application.

    The returned app exposes three endpoints:

    * ``GET /``          — serves the single-page dashboard HTML
    * ``GET /api/status`` — JSON snapshot of the latest run and experiments
    * ``WS  /ws``        — WebSocket endpoint for live event streaming
    """
    app = FastAPI(title="gradex dashboard", docs_url=None, redoc_url=None)
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> Response:
        """Serve the dashboard single-page application."""
        return templates.TemplateResponse(request=request, name="index.html")

    @app.get("/api/status")
    async def status() -> dict[str, Any]:
        """Return the current run summary and experiment list as JSON.

        Returns ``{"run": null, "experiments": []}`` when no run exists yet.
        """
        run = RunRepository().get_latest()
        if run is None:
            return {"run": None, "experiments": []}
        experiments = ExperimentRepository().list_by_run(run.id)
        return {
            "run": {
                "id": run.id,
                "benchmark_cmd": run.benchmark_cmd,
                "metric_direction": run.metric_direction,
                "baseline_score": run.baseline_score,
                "primary_language": getattr(run, "primary_language", "python"),
                "created_at": run.created_at.isoformat(),
            },
            "experiments": [
                {
                    "id": e.id[:8],
                    "full_id": e.id,
                    "status": e.status,
                    "score": e.score,
                    "gate_passed": e.gate_passed,
                    "branch": e.branch,
                    "created_at": e.created_at.isoformat(),
                }
                for e in experiments
            ],
        }

    @app.get("/api/traces/{experiment_id}")
    async def traces_endpoint(experiment_id: str) -> dict[str, Any]:
        """Return trace entries for an experiment."""
        full_id, _ = _resolve_experiment_or_404(experiment_id)
        entries = TraceReader(trace_path_for(full_id)).read_all()
        return {"experiment_id": full_id, "entries": entries}

    @app.get("/api/experiments/{experiment_id}")
    async def experiment_detail_endpoint(experiment_id: str) -> dict[str, Any]:
        """Return full experiment detail including traces."""
        return _experiment_detail_payload(experiment_id)

    @app.get("/api/analytics/{run_id}")
    async def analytics_endpoint(run_id: str) -> dict[str, Any]:
        """Full analytics for a specific run."""
        from gradex.analytics import RunAnalytics

        analytics = RunAnalytics()
        try:
            summary = analytics.get_run_summary(run_id)
            score_points = analytics.get_score_over_time(run_id)
        except KeyError:
            return {"error": "run not found"}
        return {
            "summary": {
                "run_id": summary.run_id_short,
                "baseline_score": summary.baseline_score,
                "best_score": summary.best_score,
                "improvement_pct": summary.improvement_pct,
                "improvement_abs": summary.improvement_abs,
                "duration_seconds": summary.duration_seconds,
                "breakdown": {
                    "total": summary.breakdown.total,
                    "passed": summary.breakdown.passed,
                    "rejected": summary.breakdown.rejected,
                    "failed": summary.breakdown.failed,
                    "pass_rate": summary.breakdown.pass_rate,
                },
            },
            "score_over_time": [
                {
                    "id": pt.experiment_id_short,
                    "score": pt.score,
                    "delta_from_baseline": pt.delta_from_baseline,
                    "delta_from_previous": pt.delta_from_previous,
                }
                for pt in score_points
            ],
        }

    @app.get("/api/history")
    async def history_endpoint(limit: int = 10) -> dict[str, Any]:
        """List recent runs."""
        from gradex.analytics import RunAnalytics

        analytics = RunAnalytics()
        runs = analytics.get_all_runs(limit=limit)
        return {
            "runs": [
                {
                    "run_id": r.run_id_short,
                    "baseline_score": r.baseline_score,
                    "best_score": r.best_score,
                    "improvement_pct": r.improvement_pct,
                    "total_experiments": r.breakdown.total,
                    "passed": r.breakdown.passed,
                    "pass_rate": r.breakdown.pass_rate,
                    "created_at": r.created_at.isoformat(),
                    "benchmark_cmd": r.benchmark_cmd,
                }
                for r in runs
            ]
        }

    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket) -> None:
        """Accept a WebSocket connection and register it with the broadcaster.

        The server only *pushes* events; incoming messages are discarded.
        The connection is deregistered cleanly on disconnect.
        """
        broadcaster = DashboardBroadcaster.get()
        await broadcaster.connect(ws)
        try:
            while True:
                await ws.receive_text()  # keep-alive; we push, never pull
        except WebSocketDisconnect:
            await broadcaster.disconnect(ws)

    return app
