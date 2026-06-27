"""Tests for LLM config persistence."""

from __future__ import annotations

from pathlib import Path

import pytest

from gradex.config import (
    LLMConfig,
    is_llm_configured,
    load_llm_config,
    save_llm_config,
)


def test_is_llm_configured_false_when_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "config.toml"
    monkeypatch.setattr("gradex.config.CONFIG_PATH", config_path)
    assert is_llm_configured() is False


def test_is_llm_configured_false_without_api_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "config.toml"
    monkeypatch.setattr("gradex.config.CONFIG_PATH", config_path)
    config_path.write_text('[llm]\nprovider = "groq"\n', encoding="utf-8")
    assert is_llm_configured() is False


def test_is_llm_configured_true_for_groq_with_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "config.toml"
    monkeypatch.setattr("gradex.config.CONFIG_PATH", config_path)
    save_llm_config(LLMConfig(provider="groq", api_key="gsk_test", model="x"))
    assert is_llm_configured() is True


def test_is_llm_configured_true_for_ollama_without_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "config.toml"
    monkeypatch.setattr("gradex.config.CONFIG_PATH", config_path)
    save_llm_config(LLMConfig(provider="ollama", model="llama3"))
    assert is_llm_configured() is True


def test_save_and_load_round_trip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_path = tmp_path / "config.toml"
    monkeypatch.setattr("gradex.config.CONFIG_PATH", config_path)
    original = LLMConfig(
        provider="openrouter",
        model="meta-llama/llama-3.2-3b-instruct:free",
        api_key="sk-or-v1-test",
    )
    save_llm_config(original)
    loaded = load_llm_config()
    assert loaded.provider == "openrouter"
    assert loaded.model == "meta-llama/llama-3.2-3b-instruct:free"
    assert loaded.api_key == "sk-or-v1-test"
