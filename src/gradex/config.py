"""Configuration and host-registry constants for gradex."""

from __future__ import annotations

import dataclasses
import tomllib
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# Host registry (Phase 1)
# ---------------------------------------------------------------------------

# Mapping from host name -> list of binary names to look for on PATH.
# The first binary found wins.
HOST_BINARIES: dict[str, list[str]] = {
    "claude-code": ["claude"],
    "cursor": ["cursor"],
    "copilot": ["gh"],
}

SUPPORTED_HOSTS: list[str] = list(HOST_BINARIES.keys())

# ---------------------------------------------------------------------------
# LLM configuration (Phase 5)
# ---------------------------------------------------------------------------

CONFIG_PATH: Path = Path.home() / ".gradex" / "config.toml"


@dataclass
class LLMConfig:
    """Per-user LLM provider settings loaded from ``~/.gradex/config.toml``."""

    provider: str = "groq"  # "anthropic" | "openai" | "ollama" | "groq"
    model: str = ""  # empty → use provider default
    api_key: str = ""  # not used for ollama
    ollama_base_url: str = "http://localhost:11434/v1"
    groq_base_url: str = "https://api.groq.com/openai/v1"
    max_tokens: int = 4096
    temperature: float = 0.3

    def effective_model(self) -> str:
        """Return the configured model name, falling back to the provider default."""
        if self.model:
            return self.model
        defaults: dict[str, str] = {
            "anthropic": "claude-sonnet-4-6",
            "openai": "gpt-4o",
            "ollama": "llama3",
            "groq": "llama-3.3-70b-versatile",
        }
        return defaults.get(self.provider, "llama-3.3-70b-versatile")


def load_llm_config() -> LLMConfig:
    """Load LLM config from ``~/.gradex/config.toml``.

    Returns a default :class:`LLMConfig` if the file is absent or has no
    ``[llm]`` section.  Unknown keys in the TOML ``[llm]`` table are silently
    ignored so that future config additions remain backward-compatible.
    """
    if not CONFIG_PATH.exists():
        return LLMConfig()
    with open(CONFIG_PATH, "rb") as fh:
        data = tomllib.load(fh)
    llm_section: dict[str, object] = data.get("llm", {})
    valid_fields = {f.name for f in dataclasses.fields(LLMConfig)}
    filtered = {k: v for k, v in llm_section.items() if k in valid_fields}
    return LLMConfig(**filtered)  # type: ignore[arg-type]
