"""Tests for LLMClient — all provider calls are mocked, no real API traffic."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from gradex.ai.client import LLMClient
from gradex.config import LLMConfig, load_llm_config

# ---------------------------------------------------------------------------
# Provider tests
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_anthropic_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """Anthropic path returns text and token counts from the mocked SDK."""
    mock_block = MagicMock()
    mock_block.text = "hello"
    mock_usage = MagicMock()
    mock_usage.input_tokens = 10
    mock_usage.output_tokens = 5
    mock_msg = MagicMock()
    mock_msg.content = [mock_block]
    mock_msg.usage = mock_usage

    mock_create = AsyncMock(return_value=mock_msg)
    mock_messages = MagicMock()
    mock_messages.create = mock_create
    mock_ant_instance = MagicMock()
    mock_ant_instance.messages = mock_messages
    mock_ant_class = MagicMock(return_value=mock_ant_instance)

    import anthropic

    monkeypatch.setattr(anthropic, "AsyncAnthropic", mock_ant_class)

    config = LLMConfig(provider="anthropic", api_key="sk-test")
    client = LLMClient(config)
    result = await client.complete("sys", "user")

    assert result.text == "hello"
    assert result.provider == "anthropic"
    assert result.input_tokens == 10


@pytest.mark.anyio
async def test_openai_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """OpenAI path returns message content from the mocked SDK."""
    mock_choice = MagicMock()
    mock_choice.message.content = "world"
    mock_usage = MagicMock()
    mock_usage.prompt_tokens = 8
    mock_usage.completion_tokens = 3
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    mock_resp.usage = mock_usage

    mock_create = AsyncMock(return_value=mock_resp)
    mock_completions = MagicMock()
    mock_completions.create = mock_create
    mock_chat = MagicMock()
    mock_chat.completions = mock_completions
    mock_oai_instance = MagicMock()
    mock_oai_instance.chat = mock_chat
    mock_oai_class = MagicMock(return_value=mock_oai_instance)

    import openai

    monkeypatch.setattr(openai, "AsyncOpenAI", mock_oai_class)

    config = LLMConfig(provider="openai", api_key="sk-test")
    client = LLMClient(config)
    result = await client.complete("sys", "user")

    assert result.text == "world"
    assert result.provider == "openai"


@pytest.mark.anyio
async def test_ollama_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ollama path calls httpx and parses the OpenAI-compatible response body."""
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "ollama response"}}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 2},
    }

    mock_session = AsyncMock()
    mock_session.post = AsyncMock(return_value=mock_response)

    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    mock_client_class = MagicMock(return_value=mock_cm)

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", mock_client_class)

    config = LLMConfig(provider="ollama", model="llama3")
    client = LLMClient(config)
    result = await client.complete("sys", "user")

    assert result.text == "ollama response"
    assert result.provider == "ollama"


@pytest.mark.anyio
async def test_unknown_provider_raises() -> None:
    """An unrecognised provider raises ValueError with a descriptive message."""
    config = LLMConfig(provider="cursor")
    client = LLMClient(config)
    with pytest.raises(ValueError, match="Unknown provider"):
        await client.complete("s", "u")


# ---------------------------------------------------------------------------
# LLMConfig tests
# ---------------------------------------------------------------------------


def test_default_model_anthropic() -> None:
    """Empty model string falls back to the Anthropic default."""
    config = LLMConfig(provider="anthropic", model="")
    assert config.effective_model() == "claude-sonnet-4-6"


def test_default_model_ollama() -> None:
    """Empty model string falls back to the Ollama default."""
    config = LLMConfig(provider="ollama", model="")
    assert config.effective_model() == "llama3"


def test_custom_model_overrides_default() -> None:
    """An explicit model name takes precedence over the provider default."""
    config = LLMConfig(provider="anthropic", model="claude-opus-4-6")
    assert config.effective_model() == "claude-opus-4-6"


# ---------------------------------------------------------------------------
# Config loading tests
# ---------------------------------------------------------------------------


def test_load_config_missing_file(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing config file returns the default LLMConfig (groq since Phase 7)."""
    monkeypatch.setattr("gradex.config.CONFIG_PATH", Path("/nonexistent/config.toml"))
    config = load_llm_config()
    assert config.provider == "groq"


def test_load_config_from_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A valid config.toml is parsed and overrides defaults."""
    config_file = tmp_path / "config.toml"
    config_file.write_text('[llm]\nprovider = "ollama"\nmodel = "mistral"\n')
    monkeypatch.setattr("gradex.config.CONFIG_PATH", config_file)
    config = load_llm_config()
    assert config.provider == "ollama"
    assert config.model == "mistral"
