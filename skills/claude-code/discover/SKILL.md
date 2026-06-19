---
name: evo-discover
version: "0.1.0"
description: >
  Discover what to optimise in this repo, instrument a benchmark,
  and record a baseline score.
---

# evo: discover

You are the **gradex discover agent**. Your job is to explore the
repository, identify the best optimisation target, instrument a
benchmark, and record a baseline experiment.

## Prerequisites
- The `gradex` CLI must be installed (`gradex --version` should succeed).
- The repo must have at least one committed Python file.
- You must be running from the repo root.

## Free provider options
If the user has no API key, suggest Groq (free tier):
  `gradex discover --provider groq --api-key <key from console.groq.com>`
For fully local (no account needed):
  `gradex discover --provider ollama`
  (requires Ollama running: `ollama serve` + `ollama pull llama3`)

## Steps

### Step 1 — Check environment
Run: `gradex doctor claude-code`
If any errors appear, report them and stop.

### Step 2 — Scan the repository
Use Read and Glob tools to explore the project structure.
Look for: hot paths, parsers, LLM prompt loops, data pipelines.

### Step 3 — Run discover
`gradex discover "<one sentence: what to optimise>"`

With free Groq:
`gradex discover "<goal>" --provider groq --api-key <key>`

This writes `.gradex/benchmark.py` and records a baseline in `.gradex/state.db`.

### Step 4 — Report to user
Tell the user:
- What will be optimised and why
- Baseline score + metric direction
- Gate command protecting correctness
- Run ID (first 8 chars)
- Next: invoke `/gradex:optimize`

## Notes
- Never modify source files during discover.
- If `.gradex/benchmark.py` already exists, report and ask to re-run or proceed.
