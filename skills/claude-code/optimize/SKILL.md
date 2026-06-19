---
name: evo-optimize
version: "0.1.0"
description: >
  Run the evo optimization loop — spawn parallel experiments,
  score each patch, keep only improvements that pass gates.
---

# evo: optimize

You are the **gradex optimize agent**.

## Parameters
| Parameter | Default | Description                              |
|-----------|---------|------------------------------------------|
| subagents | 3       | Parallel experiments per round           |
| budget    | 5       | Max experiments per subagent             |
| stall     | 3       | Rounds without improvement before stop   |
| provider  | groq    | anthropic / openai / groq / ollama       |

## Free provider options
Groq (recommended free):
  `gradex optimize --provider groq --api-key <key>`
Ollama (local, no account):
  `gradex optimize --provider ollama`

## Steps

### Step 1 — Confirm run exists
A run must exist from `gradex discover`. If not, tell user to run discover first.

### Step 2 — Start optimization
Default: `gradex optimize`
With params: `gradex optimize --subagents 3 --budget 10 --stall 3 --provider groq --api-key <key>`

### Step 3 — Monitor
Tell user to open in separate terminal:
`gradex dashboard`  →  http://127.0.0.1:8080

### Step 4 — Report results
When complete:
- Rounds / experiments / passed count
- Baseline vs best score + improvement %
- Stop reason (stall / budget)
- If improved: winning experiment ID
  "Review changes in `.gradex/worktrees/<id>/` before merging"

## Safety
- Main branch is NEVER modified.
- Experiment promoted ONLY IF score improved AND all gates passed.
- Ctrl+C safely stops the loop and cleans worktrees.
