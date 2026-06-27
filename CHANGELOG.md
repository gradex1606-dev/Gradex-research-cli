# Changelog

## Unreleased

## 0.1.1

### Added

- **Interactive model setup** — after `gradex install`, optional provider/model/API key wizard; `gradex configure` to re-run; `gradex models` to list options; `--no-setup` for CI.
- **OpenRouter provider** — try GradeX with free-tier models via `--provider openrouter` (opt-in; Groq remains default).
- **`gradex report`** — export a self-contained HTML run report for sharing.
- **Benchmark cache** — benchmark scores cached per git tree (24h TTL) to skip redundant runs during optimization.

### Changed

- Groq, OpenRouter, and OpenAI-compatible providers share one client code path.
- OpenRouter API keys scrubbed from traces and logs.

## 0.1.0

- Initial open-source CLI: discover, optimize, dashboard, stats, history.
- Providers: Groq, Anthropic, OpenAI, Ollama.
- Cursor and Claude Code host integrations.
