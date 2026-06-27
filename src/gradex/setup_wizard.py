"""Interactive provider and model setup wizard."""

from __future__ import annotations

import httpx
import typer
from rich.console import Console

from gradex.config import (
    CONFIG_PATH,
    CURATED_MODELS,
    DEFAULT_MODELS,
    LLMConfig,
    SUPPORTED_LLM_PROVIDERS,
    save_llm_config,
)

PROVIDER_MENU: list[tuple[str, str]] = [
    ("groq", "Groq (recommended for optimize)"),
    ("openrouter", "OpenRouter (free-tier testing)"),
    ("ollama", "Ollama (local, no key)"),
    ("anthropic", "Anthropic"),
    ("openai", "OpenAI"),
]


def list_models_for_provider(provider: str) -> list[str]:
    """Return curated (and for Ollama, local) models for *provider*."""
    if provider == "ollama":
        local = _fetch_ollama_model_names()
        if local:
            return local
    return list(CURATED_MODELS.get(provider, [DEFAULT_MODELS[provider]]))


def _fetch_ollama_model_names(base_url: str = "http://localhost:11434") -> list[str]:
    try:
        response = httpx.get(f"{base_url.rstrip('/')}/api/tags", timeout=2.0)
        response.raise_for_status()
        payload = response.json()
        models = payload.get("models", [])
        names = [str(item.get("name", "")).strip() for item in models]
        return [name for name in names if name]
    except Exception:  # noqa: BLE001
        return []


def _prompt_choice(
    console: Console,
    title: str,
    options: list[str],
    *,
    allow_skip: bool = False,
) -> int | None:
    """Print numbered *options* and return zero-based index, or None if skipped."""
    console.print()
    console.print(f"[bold]{title}[/bold]")
    for index, label in enumerate(options, start=1):
        console.print(f"  {index}) {label}")
    if allow_skip:
        console.print(f"  {len(options) + 1}) Skip for now")
    while True:
        raw = typer.prompt(">", default="1").strip()
        if not raw and allow_skip:
            return None
        try:
            choice = int(raw)
        except ValueError:
            console.print("[yellow]Enter a number from the list.[/yellow]")
            continue
        if allow_skip and choice == len(options) + 1:
            return None
        if 1 <= choice <= len(options):
            return choice - 1
        console.print("[yellow]Invalid choice. Try again.[/yellow]")


def run_model_setup(
    console: Console,
    *,
    allow_skip: bool = True,
    confirm_overwrite: bool = False,
) -> LLMConfig | None:
    """Run interactive provider, model, and API key setup."""
    if confirm_overwrite and CONFIG_PATH.exists():
        overwrite = typer.confirm(
            f"Overwrite existing config at {CONFIG_PATH}?",
            default=False,
        )
        if not overwrite:
            console.print("[dim]Setup cancelled.[/dim]")
            return None

    console.print()
    console.print("[bold]── Model setup ──[/bold]")

    provider_labels = [label for _, label in PROVIDER_MENU]
    provider_index = _prompt_choice(
        console,
        "Choose provider:",
        provider_labels,
        allow_skip=allow_skip,
    )
    if provider_index is None:
        console.print("[dim]Skipped model setup.[/dim]")
        return None

    provider = PROVIDER_MENU[provider_index][0]
    models = list_models_for_provider(provider)
    model_labels = models + ["Enter custom model ID"]
    model_index = _prompt_choice(console, "Choose model:", model_labels)
    assert model_index is not None

    if model_index == len(models):
        custom = typer.prompt("Model ID").strip()
        if not custom:
            console.print("[red]Model ID cannot be empty.[/red]")
            return None
        model = custom
    else:
        model = models[model_index]

    api_key = ""
    if provider != "ollama":
        api_key = typer.prompt("API key", hide_input=True).strip()
        if not api_key:
            console.print("[red]API key is required for this provider.[/red]")
            return None

    config = LLMConfig(provider=provider, model=model, api_key=api_key)
    path = save_llm_config(config)
    console.print(f"[green]✓[/green] Saved to {path}")
    console.print(
        f"[dim]Provider: {config.provider} / {config.effective_model()}[/dim]"
    )
    return config


def print_models(console: Console, provider: str) -> None:
    """Print curated models for *provider*."""
    if provider not in SUPPORTED_LLM_PROVIDERS:
        valid = ", ".join(SUPPORTED_LLM_PROVIDERS)
        raise ValueError(f"Unknown provider {provider!r}. Choose: {valid}")

    models = list_models_for_provider(provider)
    console.print(f"[bold]Models for {provider}:[/bold]")
    for name in models:
        default_marker = " (default)" if name == DEFAULT_MODELS.get(provider) else ""
        console.print(f"  • {name}{default_marker}")
