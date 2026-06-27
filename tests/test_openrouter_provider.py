"""Tests for OpenRouter provider support in LLMClient and LLMConfig."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from gradex.ai.client import LLMClient, LLMResponse
from gradex.config import LLMConfig


def test_openrouter_effective_model_default() -> None:
    config = LLMConfig(provider="openrouter")
    assert config.effective_model() == "meta-llama/llama-3.2-3b-instruct:free"


def test_openrouter_base_url_default() -> None:
    config = LLMConfig()
    assert "openrouter.ai" in config.openrouter_base_url


def test_openrouter_model_override() -> None:
    config = LLMConfig(provider="openrouter", model="google/gemma-2-9b-it:free")
    assert config.effective_model() == "google/gemma-2-9b-it:free"


def test_unknown_provider_error_includes_openrouter() -> None:
    config = LLMConfig(provider="invalid-provider")
    client = LLMClient(config)
    with pytest.raises(ValueError, match="openrouter"):
        asyncio.run(client.complete("sys", "user"))


@pytest.mark.anyio
async def test_openrouter_provider_dispatched(monkeypatch: pytest.MonkeyPatch) -> None:
    config = LLMConfig(provider="openrouter", api_key="test-key")
    client = LLMClient(config)

    called: list[bool] = []

    async def _mock_openrouter(system: str, user: str, max_tokens: int) -> LLMResponse:
        called.append(True)
        return LLMResponse(
            text="mock",
            input_tokens=5,
            output_tokens=5,
            provider="openrouter",
            model="meta-llama/llama-3.2-3b-instruct:free",
        )

    monkeypatch.setattr(client, "_complete_openrouter", _mock_openrouter)
    resp = await client.complete("system", "user")

    assert called
    assert resp.provider == "openrouter"


@pytest.mark.anyio
async def test_openrouter_complete_uses_base_url_and_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import openai

    captured: dict[str, object] = {}

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "hello from openrouter"
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

    config = LLMConfig(provider="openrouter", api_key="sk-or-v1-test")
    client = LLMClient(config)
    resp = await client.complete("system", "user")

    assert resp.provider == "openrouter"
    assert resp.text == "hello from openrouter"
    assert captured.get("base_url") == config.openrouter_base_url
    headers = captured.get("default_headers")
    assert isinstance(headers, dict)
    assert headers.get("HTTP-Referer") == "https://gradex.dev"
    assert headers.get("X-Title") == "GradeX"
