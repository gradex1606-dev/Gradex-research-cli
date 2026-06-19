"""Tests for the CLI subcommands via typer's test runner."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from gradex.cli import app

runner = CliRunner()


def test_help_lists_all_subcommands() -> None:
    """gradex --help should list all four subcommands."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in ("install", "doctor", "dashboard", "upgrade"):
        assert cmd in result.output, f"'{cmd}' missing from --help output"


def test_version_flag() -> None:
    """--version should print the version string and exit cleanly."""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "gradex version" in result.output


def test_install_unknown_host_exits_nonzero() -> None:
    """install with an unknown host should exit non-zero with an error message."""
    result = runner.invoke(app, ["install", "no-such-host"])
    assert result.exit_code != 0
    assert "no-such-host" in result.output


def test_dashboard_starts(monkeypatch: pytest.MonkeyPatch) -> None:
    """dashboard command prints the URL and delegates to uvicorn (mocked)."""
    import uvicorn

    called: list[dict[str, object]] = []
    monkeypatch.setattr(uvicorn, "run", lambda *a, **kw: called.append(kw))

    result = runner.invoke(app, ["dashboard", "--port", "19998", "--no-browser"])
    assert result.exit_code == 0
    assert "Dashboard live" in result.output
    assert called[0]["port"] == 19998


def test_upgrade_checks_pypi(monkeypatch: pytest.MonkeyPatch) -> None:
    """upgrade should check PyPI and report up-to-date status."""
    from gradex import __version__

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, dict[str, str]]:
            return {"info": {"version": __version__}}

    class FakeClient:
        async def __aenter__(self) -> FakeClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def get(self, url: str) -> FakeResponse:
            return FakeResponse()

    monkeypatch.setattr("gradex.cli.httpx.AsyncClient", lambda **kwargs: FakeClient())

    result = runner.invoke(app, ["upgrade"])
    assert result.exit_code == 0
    assert "up to date" in result.output


def test_doctor_unknown_host_exits_nonzero() -> None:
    """doctor with an unknown host should exit non-zero."""
    result = runner.invoke(app, ["doctor", "no-such-host"])
    assert result.exit_code != 0


def test_doctor_output_structure() -> None:
    """doctor should print a header line mentioning the host name."""
    result = runner.invoke(app, ["doctor", "claude-code"])
    assert "claude-code" in result.output
