"""Tests for the CLI subcommands via typer's test runner."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from gradex.cli import app
from gradex.config import LLMConfig
from gradex.hosts.base import InstallResult

runner = CliRunner()


def test_help_lists_all_subcommands() -> None:
    """gradex --help should list core subcommands."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in (
        "install",
        "configure",
        "models",
        "doctor",
        "dashboard",
        "upgrade",
    ):
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


def _mock_successful_installer(tmp_path: Path) -> MagicMock:
    installer = MagicMock()
    installer.display_name = "Cursor"
    installer.install.return_value = InstallResult(
        success=True,
        host="cursor",
        plugin_dir=tmp_path / ".cursor" / "rules",
        files_written=["evo-discover.mdc", "evo-optimize.mdc"],
        message="",
    )
    return installer


def test_install_no_setup_skips_wizard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """install --no-setup should not invoke the model setup wizard."""
    setup_called: list[bool] = []

    def fake_setup(*args: object, **kwargs: object) -> None:
        setup_called.append(True)
        return None

    monkeypatch.setattr("gradex.setup_wizard.run_model_setup", fake_setup)
    monkeypatch.setattr(
        "gradex.hosts.get_installer",
        lambda host: _mock_successful_installer(tmp_path),
    )
    monkeypatch.setattr("gradex.config.is_llm_configured", lambda: False)

    result = runner.invoke(app, ["install", "cursor", "--no-setup"])
    assert result.exit_code == 0
    assert setup_called == []


def test_install_runs_setup_when_unconfigured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """install should run model setup when LLM config is missing."""
    setup_called: list[bool] = []

    def fake_setup(*args: object, **kwargs: object) -> LLMConfig:
        setup_called.append(True)
        return LLMConfig(provider="groq", api_key="test", model="x")

    monkeypatch.setattr("gradex.setup_wizard.run_model_setup", fake_setup)
    monkeypatch.setattr(
        "gradex.hosts.get_installer",
        lambda host: _mock_successful_installer(tmp_path),
    )
    monkeypatch.setattr("gradex.config.is_llm_configured", lambda: False)

    result = runner.invoke(app, ["install", "cursor"])
    assert result.exit_code == 0
    assert setup_called == [True]
    assert "gradex discover" in result.output


def test_configure_command_exists(monkeypatch: pytest.MonkeyPatch) -> None:
    """configure should appear in help and accept invocation."""
    help_result = runner.invoke(app, ["configure", "--help"])
    assert help_result.exit_code == 0
    assert "LLM provider" in help_result.output

    saved: list[LLMConfig] = []

    def fake_setup(*args: object, **kwargs: object) -> LLMConfig:
        config = LLMConfig(provider="groq", api_key="k", model="m")
        saved.append(config)
        return config

    monkeypatch.setattr("gradex.setup_wizard.run_model_setup", fake_setup)
    monkeypatch.setattr("gradex.config.is_llm_configured", lambda: False)

    result = runner.invoke(app, ["configure"])
    assert result.exit_code == 0
    assert saved
    assert "gradex discover" in result.output


def test_models_lists_provider_models() -> None:
    """models should print curated models for a provider."""
    result = runner.invoke(app, ["models", "--provider", "groq"])
    assert result.exit_code == 0
    assert "llama-3.3-70b-versatile" in result.output

