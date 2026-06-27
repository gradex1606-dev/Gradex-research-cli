"""Configuration and host-registry constants for gradex."""

from __future__ import annotations

import dataclasses
import os
import stat
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

SUPPORTED_LLM_PROVIDERS: tuple[str, ...] = (
    "groq",
    "openrouter",
    "ollama",
    "anthropic",
    "openai",
)

DEFAULT_MODELS: dict[str, str] = {
    "anthropic": "claude-sonnet-4-6",
    "openai": "gpt-4o",
    "ollama": "llama3",
    "groq": "llama-3.3-70b-versatile",
    "openrouter": "meta-llama/llama-3.2-3b-instruct:free",
}

CURATED_MODELS: dict[str, list[str]] = {
    "groq": [
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
    ],
    "openrouter": [
        "meta-llama/llama-3.2-3b-instruct:free",
        "google/gemma-2-9b-it:free",
    ],
    "ollama": ["llama3", "mistral", "codellama"],
    "anthropic": [
        "claude-sonnet-4-6",
        "claude-opus-4-6",
    ],
    "openai": [
        "gpt-4o",
        "gpt-4o-mini",
    ],
}


@dataclass
class LLMConfig:
    """Per-user LLM provider settings loaded from ``~/.gradex/config.toml``."""

    provider: str = "groq"  # anthropic | openai | ollama | groq | openrouter
    model: str = ""  # empty → use provider default
    api_key: str = ""  # not used for ollama
    ollama_base_url: str = "http://localhost:11434/v1"
    groq_base_url: str = "https://api.groq.com/openai/v1"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    max_tokens: int = 4096
    temperature: float = 0.3

    def effective_model(self) -> str:
        """Return the configured model name, falling back to the provider default."""
        if self.model:
            return self.model
        return DEFAULT_MODELS.get(self.provider, "llama-3.3-70b-versatile")


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
    if not llm_section:
        return LLMConfig()
    valid_fields = {f.name for f in dataclasses.fields(LLMConfig)}
    filtered = {k: v for k, v in llm_section.items() if k in valid_fields}
    return LLMConfig(**filtered)  # type: ignore[arg-type]


def is_llm_configured() -> bool:
    """Return True when saved config has a provider and required credentials."""
    if not CONFIG_PATH.exists():
        return False
    with open(CONFIG_PATH, "rb") as fh:
        data = tomllib.load(fh)
    llm_section: dict[str, object] = data.get("llm", {})
    if not llm_section:
        return False
    provider = str(llm_section.get("provider", "")).strip()
    if provider not in SUPPORTED_LLM_PROVIDERS:
        return False
    if provider == "ollama":
        return True
    api_key = str(llm_section.get("api_key", "")).strip()
    return bool(api_key)


def _toml_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _config_to_toml(config: LLMConfig) -> str:
    lines = [
        "[llm]",
        f"provider = {_toml_string(config.provider)}",
    ]
    if config.model:
        lines.append(f"model = {_toml_string(config.model)}")
    if config.api_key:
        lines.append(f"api_key = {_toml_string(config.api_key)}")
    if config.ollama_base_url != LLMConfig().ollama_base_url:
        lines.append(f"ollama_base_url = {_toml_string(config.ollama_base_url)}")
    if config.groq_base_url != LLMConfig().groq_base_url:
        lines.append(f"groq_base_url = {_toml_string(config.groq_base_url)}")
    if config.openrouter_base_url != LLMConfig().openrouter_base_url:
        lines.append(
            f"openrouter_base_url = {_toml_string(config.openrouter_base_url)}"
        )
    if config.max_tokens != LLMConfig().max_tokens:
        lines.append(f"max_tokens = {config.max_tokens}")
    if config.temperature != LLMConfig().temperature:
        lines.append(f"temperature = {config.temperature}")
    return "\n".join(lines) + "\n"


def save_llm_config(config: LLMConfig) -> Path:
    """Write *config* to :data:`CONFIG_PATH` with restrictive permissions."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        try:
            os.chmod(CONFIG_PATH.parent, stat.S_IRWXU)
        except OSError:
            pass
    CONFIG_PATH.write_text(_config_to_toml(config), encoding="utf-8")
    if os.name != "nt":
        try:
            os.chmod(CONFIG_PATH, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass
    return CONFIG_PATH
