# Gradex — autonomous code optimization. Measurable improvement, every run.

[![PyPI version](https://img.shields.io/pypi/v/gradex.svg)](https://pypi.org/project/gradex/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

Gradex discovers performance targets, captures a baseline, runs autonomous optimization experiments, and ships the best verified patch.

## Install

```bash
pip install gradex
```

## 60-Second Quickstart

```bash
pip install gradex
gradex install cursor          # one-time provider + model setup
gradex discover "make this repo faster"
gradex optimize
gradex dashboard
```

After install, GradeX walks you through provider, model, and API key setup (or skip and use CLI flags). Re-run anytime with `gradex configure`. Use `gradex install cursor --no-setup` in CI.

## Providers

| Provider | Best for | Notes |
|---|---|---|
| Groq | Free cloud runs | Default. Best for serious `optimize` runs |
| OpenRouter | Low-friction testing | Free-tier models; one API key, many models |
| Anthropic | High quality reasoning | Strong patch planning and code edits |
| OpenAI | General purpose | Broad model options |
| Ollama | Local/private | Runs fully on your machine |

## CLI Reference

| Command | Description |
|---|---|
| `gradex install <host>` | Installs Gradex integration for a coding host (optional one-time model setup) |
| `gradex configure` | Set up or update LLM provider, model, and API key |
| `gradex models` | List recommended models for a provider |
| `gradex doctor <host>` | Checks host environment and setup health |
| `gradex dashboard` | Starts live optimization dashboard |
| `gradex upgrade` | Checks PyPI for newer Gradex versions |
| `gradex discover [hint]` | Discovers benchmark target and baseline (Python or Node repos) |
| `gradex optimize` | Runs autonomous optimization loop |
| `gradex stats` | Shows run analytics, LLM token usage, and optional exports |
| `gradex traces` | Shows experiment trace timeline |
| `gradex report` | Exports a shareable HTML run report |
| `gradex history` | Lists recent optimization runs |

## How It Works

```text
+-----------+     +-----------+     +----------------------+     +----------------+
| discover  | --> | baseline  | --> | optimize loop (N)    | --> | best patch out |
+-----------+     +-----------+     +----------------------+     +----------------+
```

1. `discover` analyzes your repo and creates a measurable benchmark target.
2. Gradex records a baseline score.
3. `optimize` runs parallel experiment rounds (patch -> benchmark -> gate checks).
4. Best validated patch and run analytics are surfaced in dashboard and CLI.

**Dashboard:** click any experiment row for detail and trace timeline. **Stats** includes estimated LLM cost per run.

## License

MIT
