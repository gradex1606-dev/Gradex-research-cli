"""Unified LLM client supporting Anthropic, OpenAI, Ollama, Groq, and OpenRouter."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from threading import Lock

from gradex.config import LLMConfig, load_llm_config

_rate_limiters: dict[str, _TokenBucket] = {}
_rl_lock = Lock()


class _TokenBucket:
    """Token bucket limiter for max requests per 60 seconds."""

    def __init__(self, max_requests: int = 50) -> None:
        self._max = max_requests
        self._tokens = float(max_requests)
        self._last_refill = time.monotonic()
        self._lock = Lock()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        refill = elapsed * (self._max / 60.0)
        self._tokens = min(self._max, self._tokens + refill)
        self._last_refill = now

    def consume(self) -> float:
        """Consume one token; return wait seconds if throttled."""
        with self._lock:
            self._refill()
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return 0.0
            return (1.0 - self._tokens) / (self._max / 60.0)


def _get_bucket(provider: str) -> _TokenBucket:
    with _rl_lock:
        if provider not in _rate_limiters:
            _rate_limiters[provider] = _TokenBucket(max_requests=50)
        return _rate_limiters[provider]


@dataclass
class LLMResponse:
    """The result of a single LLM completion call."""

    text: str
    input_tokens: int
    output_tokens: int
    provider: str
    model: str


class LLMClient:
    """Unified LLM client supporting Anthropic, OpenAI, Ollama, Groq, and OpenRouter.

    All three backends implement the same interface: a system prompt plus a
    user prompt produce a text response.  Provider SDKs are imported lazily
    so the package can be installed without requiring all of them.
    """

    def __init__(self, config: LLMConfig | None = None) -> None:
        self._config: LLMConfig = config if config is not None else load_llm_config()

    async def complete(
        self,
        system: str,
        user: str,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Send a system+user prompt and return the assistant response.

        Args:
            system:     System prompt text.
            user:       User message text.
            max_tokens: Token budget; defaults to ``config.max_tokens``.

        Raises:
            ValueError: When the configured provider is not recognised.
        """
        cfg = self._config
        tokens = max_tokens if max_tokens is not None else cfg.max_tokens
        provider = cfg.provider
        bucket = _get_bucket(provider)

        for attempt in range(3):
            wait = bucket.consume()
            if wait == 0.0:
                break
            backoff = wait * (2**attempt)
            await asyncio.sleep(backoff)

        if provider == "anthropic":
            return await self._complete_anthropic(system, user, tokens)
        elif provider == "openai":
            return await self._complete_openai(system, user, tokens)
        elif provider == "ollama":
            return await self._complete_ollama(system, user, tokens)
        elif provider == "groq":
            return await self._complete_groq(system, user, tokens)
        elif provider == "openrouter":
            return await self._complete_openrouter(system, user, tokens)
        else:
            raise ValueError(
                f"Unknown provider: {provider!r}. "
                f"Choose: anthropic, openai, ollama, groq, openrouter"
            )

    # ------------------------------------------------------------------
    # Provider implementations
    # ------------------------------------------------------------------

    async def _complete_anthropic(
        self, system: str, user: str, max_tokens: int
    ) -> LLMResponse:
        """Call the Anthropic Messages API."""
        import anthropic as ant

        client = ant.AsyncAnthropic(api_key=self._config.api_key or None)
        msg = await client.messages.create(
            model=self._config.effective_model(),
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return LLMResponse(
            text=msg.content[0].text,  # type: ignore[union-attr]  # always TextBlock in practice
            input_tokens=msg.usage.input_tokens,
            output_tokens=msg.usage.output_tokens,
            provider="anthropic",
            model=self._config.effective_model(),
        )

    async def _complete_openai(
        self, system: str, user: str, max_tokens: int
    ) -> LLMResponse:
        """Call the OpenAI Chat Completions API."""
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=self._config.api_key or None)
        resp = await client.chat.completions.create(
            model=self._config.effective_model(),
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        choice = resp.choices[0]
        usage = resp.usage
        return LLMResponse(
            text=choice.message.content or "",
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            provider="openai",
            model=self._config.effective_model(),
        )

    async def _complete_groq(
        self, system: str, user: str, max_tokens: int
    ) -> LLMResponse:
        """Call Groq's OpenAI-compatible endpoint via the OpenAI SDK.

        Groq free tier: 14,400 requests/day.
        Get a key at https://console.groq.com.
        Best free model: ``llama-3.3-70b-versatile``.
        """
        return await self._complete_openai_compatible(
            base_url=self._config.groq_base_url,
            provider="groq",
            system=system,
            user=user,
            max_tokens=max_tokens,
        )

    async def _complete_openrouter(
        self, system: str, user: str, max_tokens: int
    ) -> LLMResponse:
        """Call OpenRouter's OpenAI-compatible endpoint.

        OpenRouter offers free-tier models for testing.
        Get a key at https://openrouter.ai/keys.
        Default free model: ``meta-llama/llama-3.2-3b-instruct:free``.
        For serious ``optimize`` runs, prefer Groq or a paid model.
        """
        return await self._complete_openai_compatible(
            base_url=self._config.openrouter_base_url,
            provider="openrouter",
            system=system,
            user=user,
            max_tokens=max_tokens,
            extra_headers={
                "HTTP-Referer": "https://gradex.dev",
                "X-Title": "GradeX",
            },
        )

    async def _complete_openai_compatible(
        self,
        base_url: str,
        provider: str,
        system: str,
        user: str,
        max_tokens: int,
        extra_headers: dict[str, str] | None = None,
    ) -> LLMResponse:
        """Shared OpenAI-compatible chat completion (Groq, OpenRouter, etc.)."""
        from openai import AsyncOpenAI

        client_kwargs: dict[str, object] = {
            "api_key": self._config.api_key or None,
            "base_url": base_url,
        }
        if extra_headers:
            client_kwargs["default_headers"] = extra_headers

        client = AsyncOpenAI(**client_kwargs)
        resp = await client.chat.completions.create(
            model=self._config.effective_model(),
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=self._config.temperature,
        )
        choice = resp.choices[0]
        usage = resp.usage
        return LLMResponse(
            text=choice.message.content or "",
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            provider=provider,
            model=self._config.effective_model(),
        )

    async def _complete_ollama(
        self, system: str, user: str, max_tokens: int
    ) -> LLMResponse:
        """Call Ollama's OpenAI-compatible endpoint via httpx.

        Ollama exposes ``http://localhost:11434/v1`` — no extra SDK required.
        """

        import httpx

        payload = {
            "model": self._config.effective_model(),
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "options": {"num_predict": max_tokens},
        }
        async with httpx.AsyncClient(timeout=120.0) as http:
            resp = await http.post(
                f"{self._config.ollama_base_url}/chat/completions",
                json=payload,
            )
        resp.raise_for_status()
        data: dict[str, object] = resp.json()
        choices = data["choices"]
        text: str = choices[0]["message"]["content"]  # type: ignore[index]
        usage: dict[str, int] = data.get("usage", {})  # type: ignore[assignment]  # resp.json() is untyped
        return LLMResponse(
            text=text,
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            provider="ollama",
            model=self._config.effective_model(),
        )
