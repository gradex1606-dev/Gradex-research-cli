"""Tests for interactive model setup wizard."""

from __future__ import annotations

from pathlib import Path

import pytest
from rich.console import Console

from gradex.config import LLMConfig
from gradex.setup_wizard import list_models_for_provider, run_model_setup


def test_list_models_for_provider_groq() -> None:
    models = list_models_for_provider("groq")
    assert "llama-3.3-70b-versatile" in models


def test_run_model_setup_skip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_path = tmp_path / "config.toml"
    monkeypatch.setattr("gradex.config.CONFIG_PATH", config_path)
    monkeypatch.setattr("gradex.setup_wizard.typer.prompt", lambda *a, **k: "6")

    console = Console(force_terminal=True, width=80)
    result = run_model_setup(console, allow_skip=True)
    assert result is None
    assert not config_path.exists()


def test_run_model_setup_saves_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "config.toml"
    monkeypatch.setattr("gradex.config.CONFIG_PATH", config_path)
    prompts = iter(["1", "1", "secret-key"])
    monkeypatch.setattr(
        "gradex.setup_wizard.typer.prompt",
        lambda *args, **kwargs: next(prompts),
    )

    console = Console(force_terminal=True, width=80)
    result = run_model_setup(console, allow_skip=True)
    assert result is not None
    assert result.provider == "groq"
    assert result.api_key == "secret-key"
    assert config_path.exists()


def test_run_model_setup_custom_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "config.toml"
    monkeypatch.setattr("gradex.config.CONFIG_PATH", config_path)
    groq_models = list_models_for_provider("groq")
    custom_index = len(groq_models) + 1
    prompts = iter(["2", str(custom_index), "my/custom:free", "or-key"])
    monkeypatch.setattr(
        "gradex.setup_wizard.typer.prompt",
        lambda *args, **kwargs: next(prompts),
    )

    console = Console(force_terminal=True, width=80)
    result = run_model_setup(console, allow_skip=True)
    assert result is not None
    assert result.provider == "openrouter"
    assert result.model == "my/custom:free"


def test_run_model_setup_ollama_skips_api_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "config.toml"
    monkeypatch.setattr("gradex.config.CONFIG_PATH", config_path)
    monkeypatch.setattr(
        "gradex.setup_wizard._fetch_ollama_model_names",
        lambda *a, **k: [],
    )
    prompts = iter(["3", "1"])
    monkeypatch.setattr(
        "gradex.setup_wizard.typer.prompt",
        lambda *args, **kwargs: next(prompts),
    )

    console = Console(force_terminal=True, width=80)
    result = run_model_setup(console, allow_skip=True)
    assert result is not None
    assert result.provider == "ollama"
    assert result.api_key == ""
