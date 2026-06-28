# Changelog

## Unreleased

## 0.2.0

### Added

- **Dashboard experiment detail** — click an experiment row to open metadata + trace timeline.
- **`gradex traces`** — view JSONL trace entries from the CLI.
- **Cost visibility in `gradex stats`** — token totals and estimated USD cost in stats, JSON/CSV/HTML export.
- **Node/TypeScript discover** — `gradex discover` detects `package.json` repos and writes `.gradex/benchmark.mjs` with `npm test` gates.

### Changed

- Experiment traces written on failure; `traces_path` and token usage persisted on each experiment.
- Dashboard status API returns full experiment IDs for drill-down.

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
