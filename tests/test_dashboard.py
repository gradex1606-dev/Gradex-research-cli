"""Tests for the live dashboard: HTTP routes, WebSocket broadcast, and port selection."""

from __future__ import annotations

import json
import socket
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from typer.testing import CliRunner

import gradex.state as state_module
from gradex.cli import app as cli_app
from gradex.dashboard.broadcaster import DashboardBroadcaster
from gradex.dashboard.server import create_app, find_free_port
from gradex.repository import ExperimentRepository, RunRepository

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

cli_runner = CliRunner()


@pytest.fixture
def anyio_backend() -> str:
    """Force anyio to use the asyncio backend for all async tests here."""
    return "asyncio"


@pytest.fixture(autouse=True)
def reset_broadcaster() -> Iterator[None]:
    """Ensure the DashboardBroadcaster singleton is clean before and after each test."""
    DashboardBroadcaster.reset()
    yield
    DashboardBroadcaster.reset()


@pytest.fixture
def db_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Redirect all DB access to a fresh tmp_path DB for the duration of the test."""
    evo_dir = tmp_path / ".gradex"
    monkeypatch.setattr(state_module, "GRADEX_DIR", evo_dir)
    monkeypatch.setattr(state_module, "DB_PATH", evo_dir / "state.db")


# ---------------------------------------------------------------------------
# HTTP route tests
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_index_returns_html(db_env: None) -> None:
    """GET / returns 200 HTML containing the dashboard title."""
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "gradex dashboard" in response.text


@pytest.mark.anyio
async def test_status_no_run(db_env: None) -> None:
    """GET /api/status returns the empty sentinel when no run exists."""
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/status")
    assert response.status_code == 200
    assert response.json() == {"run": None, "experiments": []}


@pytest.mark.anyio
async def test_status_with_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    db_env: None,
) -> None:
    """GET /api/status reflects a created run and its experiments."""
    run = RunRepository().create("bench", "higher", [], 1.0)
    exp_repo = ExperimentRepository()
    exp_repo.create(run.id, None, "branch-a")
    exp_repo.create(run.id, None, "branch-b")

    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/status")

    assert response.status_code == 200
    data: dict[str, Any] = response.json()
    assert data["run"]["id"] == run.id
    assert len(data["experiments"]) == 2
    assert "full_id" in data["experiments"][0]


@pytest.mark.anyio
async def test_traces_endpoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    db_env: None,
) -> None:
    """GET /api/traces/{id} returns trace entries."""
    from gradex.traces import TraceWriter, trace_path_for

    run = RunRepository().create("bench", "higher", [], 1.0)
    exp = ExperimentRepository().create(run.id, None, "branch-a")
    TraceWriter(trace_path_for(exp.id)).write("info", "started", {"n": 1})

    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(f"/api/traces/{exp.id[:8]}")

    assert response.status_code == 200
    data = response.json()
    assert data["experiment_id"] == exp.id
    assert len(data["entries"]) == 1


@pytest.mark.anyio
async def test_experiment_detail_endpoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    db_env: None,
) -> None:
    """GET /api/experiments/{id} returns metadata and traces."""
    from gradex.traces import TraceWriter, trace_path_for

    run = RunRepository().create("bench", "higher", [], 1.0)
    exp = ExperimentRepository().create(run.id, None, "branch-a")
    ExperimentRepository().update_llm_usage(exp.id, 10, 5, "gpt-4o")
    TraceWriter(trace_path_for(exp.id)).write("info", "gate", {"passed": True})

    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(f"/api/experiments/{exp.id}")

    assert response.status_code == 200
    data = response.json()
    assert data["experiment"]["branch"] == "branch-a"
    assert data["experiment"]["input_tokens"] == 10
    assert len(data["traces"]) == 1


@pytest.mark.anyio
async def test_experiment_detail_not_found(db_env: None) -> None:
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/experiments/no-such-id")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# WebSocket / broadcaster test
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_websocket_broadcast() -> None:
    """broadcast() delivers a JSON event to every registered client."""
    broadcaster = DashboardBroadcaster.get()
    received: list[str] = []

    class _FakeWS:
        """Minimal mock that satisfies DashboardBroadcaster.connect / send_text."""

        async def accept(self) -> None:
            pass

        async def send_text(self, data: str) -> None:
            received.append(data)

    await broadcaster.connect(_FakeWS())  # type: ignore[arg-type]
    await broadcaster.broadcast({"type": "log", "msg": "hello"})

    assert len(received) == 1
    event = json.loads(received[0])
    assert event["type"] == "log"
    assert event["msg"] == "hello"


# ---------------------------------------------------------------------------
# Port-selection utility
# ---------------------------------------------------------------------------


def test_find_free_port() -> None:
    """find_free_port skips an already-bound port and returns the next free one."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 18080))
        port = find_free_port(18080)
    assert port > 18080


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------


def test_port_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    """dashboard --port N --no-browser prints the URL and calls uvicorn.run."""
    import uvicorn

    called: list[dict[str, Any]] = []
    monkeypatch.setattr(uvicorn, "run", lambda *a, **kw: called.append(kw))

    result = cli_runner.invoke(
        cli_app, ["dashboard", "--port", "19999", "--no-browser"]
    )
    assert result.exit_code == 0
    assert "Dashboard live" in result.output
    assert called[0]["port"] == 19999
