"""Tests for Groq provider support in LLMClient and LLMConfig."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from gradex.ai.client import LLMClient, LLMResponse
from gradex.config import LLMConfig

# ---------------------------------------------------------------------------
# LLMConfig tests
# ---------------------------------------------------------------------------


def test_groq_is_default_provider() -> None:
    """LLMConfig defaults to 'groq' provider."""
    config = LLMConfig()
    assert config.provider == "groq"


def test_groq_effective_model_default() -> None:
    """groq provider resolves to the versatile llama model by default."""
    config = LLMConfig(provider="groq")
    assert config.effective_model() == "llama-3.3-70b-versatile"


def test_groq_model_override() -> None:
    """An explicit model string overrides the provider default."""
    config = LLMConfig(provider="groq", model="llama-3.1-8b-instant")
    assert config.effective_model() == "llama-3.1-8b-instant"


def test_groq_base_url_default() -> None:
    """groq_base_url defaults to the Groq API endpoint."""
    config = LLMConfig()
    assert "groq.com" in config.groq_base_url


def test_unknown_provider_error_includes_groq() -> None:
    """ValueError for an unknown provider names 'groq' in the message."""
    config = LLMConfig(provider="invalid-provider")
    client = LLMClient(config)
    with pytest.raises(ValueError, match="groq"):
        asyncio.run(client.complete("sys", "user"))


# ---------------------------------------------------------------------------
# LLMClient dispatch tests
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_groq_provider_dispatched(monkeypatch: pytest.MonkeyPatch) -> None:
    """complete() calls _complete_groq when provider='groq'."""
    config = LLMConfig(provider="groq", api_key="test-key")
    client = LLMClient(config)

    called: list[bool] = []

    async def _mock_groq(system: str, user: str, max_tokens: int) -> LLMResponse:
        called.append(True)
        return LLMResponse(
            text="mock",
            input_tokens=5,
            output_tokens=5,
            provider="groq",
            model="llama-3.3-70b-versatile",
        )

    monkeypatch.setattr(client, "_complete_groq", _mock_groq)
    resp = await client.complete("system", "user")

    assert called, "_complete_groq was not called"
    assert resp.provider == "groq"


@pytest.mark.anyio
async def test_groq_complete_uses_groq_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_complete_groq constructs AsyncOpenAI with the Groq base_url."""
    import openai

    captured: dict[str, object] = {}

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "hello from groq"
    mock_response.usage.prompt_tokens = 10
    mock_response.usage.completion_tokens = 20

    mock_completions = AsyncMock()
    mock_completions.create.return_value = mock_response

    class MockAsyncOpenAI:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)
            self.chat = MagicMock()
            self.chat.completions = mock_completions

    monkeypatch.setattr(openai, "AsyncOpenAI", MockAsyncOpenAI)

    config = LLMConfig(provider="groq", api_key="gsk_test")
    client = LLMClient(config)
    resp = await client.complete("system", "user")

    assert resp.provider == "groq"
    assert resp.text == "hello from groq"
    assert captured.get("base_url") == config.groq_base_url
    assert captured.get("api_key") == "gsk_test"


@pytest.mark.anyio
async def test_groq_complete_response_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_complete_groq maps usage tokens to LLMResponse fields correctly."""
    import openai

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "response text"
    mock_response.usage.prompt_tokens = 15
    mock_response.usage.completion_tokens = 25

    mock_completions = AsyncMock()
    mock_completions.create.return_value = mock_response

    class MockAsyncOpenAI:
        def __init__(self, **kwargs: object) -> None:
            self.chat = MagicMock()
            self.chat.completions = mock_completions

    monkeypatch.setattr(openai, "AsyncOpenAI", MockAsyncOpenAI)

    config = LLMConfig(provider="groq", api_key="key")
    client = LLMClient(config)
    resp = await client.complete("sys", "usr")

    assert resp.input_tokens == 15
    assert resp.output_tokens == 25
    assert resp.model == config.effective_model()
