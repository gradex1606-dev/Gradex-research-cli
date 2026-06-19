import sys
from pathlib import Path

sys.path.insert(0, "src")

import gradex.state as state_mod  # noqa: E402

SEED_DIR = Path("_seed_demo")
SEED_DIR.mkdir(exist_ok=True)
state_mod.GRADEX_DIR = SEED_DIR
state_mod.DB_PATH = SEED_DIR / "state.db"

import gradex.backends.worktree as wt_mod  # noqa: E402

wt_mod.GRADEX_DIR = SEED_DIR

from gradex.repository import ExperimentRepository, RunRepository  # noqa: E402
from gradex.traces import TraceWriter  # noqa: E402

run_repo = RunRepository()
exp_repo = ExperimentRepository()

run = run_repo.create(
    benchmark_cmd="python bench.py",
    metric_direction="lower",
    gate_cmds=["pytest tests/"],
    baseline_score=41.2,
)

statuses = [
    ("passed", 38.1, True),
    ("rejected", 29.0, False),
    ("passed", 35.6, True),
    ("failed", None, None),
    ("passed", 31.4, True),
    ("running", None, None),
    ("pending", None, None),
]

for i, (status, score, gate_passed) in enumerate(statuses):
    exp = exp_repo.create(run.id, None, f"gradex/exp-00{i + 1}")
    if score is not None:
        exp_repo.update_score(exp.id, score, gate_passed, status)
    tw = TraceWriter(SEED_DIR / "traces" / f"{exp.id}.jsonl")
    tw.write("info", f"Experiment {i + 1} started")
    tw.write("info", "Running benchmark: python bench.py")
    if score:
        tw.write("info", f"Score: {score}")
    if status == "rejected":
        tw.write("error", "Gate failed: 2 tests failed")

run_repo.update_baseline_experiment(run.id, exp_repo.list_by_run(run.id)[0].id)
print(f"Seeded run {run.id[:8]} with {len(statuses)} experiments")
print("Now run: python -m gradex dashboard")
