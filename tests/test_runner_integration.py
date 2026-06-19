"""End-to-end integration test: WorktreeBackend + BenchmarkRunner + GateRunner."""

from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path

import pytest

from gradex.backends.worktree import WorktreeBackend
from gradex.runner.benchmark import BenchmarkRunner
from gradex.runner.gate import GateRunner

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def patch_evo_dir(git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect GRADEX_DIR into the test git repo so worktrees are isolated."""
    evo_dir = git_repo / ".gradex"
    monkeypatch.setattr("gradex.state.GRADEX_DIR", evo_dir)
    monkeypatch.setattr("gradex.backends.worktree.GRADEX_DIR", evo_dir)


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_benchmark_and_gate_in_worktree(
    git_repo: Path, patch_evo_dir: None
) -> None:
    """Full pipeline: create worktree, run benchmark, run gate, then clean up."""
    # --- commit bench.py to the repo so the worktree inherits it ---
    bench_src = textwrap.dedent("""\
        import time
        import random
        time.sleep(0.05)
        print(f"{random.uniform(10, 20):.4f}")
    """)
    (git_repo / "bench.py").write_text(bench_src)
    subprocess.run(
        ["git", "add", "bench.py"], cwd=git_repo, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "add bench"],
        cwd=git_repo,
        check=True,
        capture_output=True,
    )

    backend = WorktreeBackend(repo_root=git_repo)
    workspace = await backend.create_workspace("integ-001")

    try:
        # --- benchmark ---
        bench_result = await BenchmarkRunner(backend).run(
            workspace, ["python", "bench.py"]
        )
        assert bench_result.score is not None, (
            f"parse_error: {bench_result.parse_error}"
        )
        assert 10.0 <= bench_result.score <= 20.0

        # --- write gate script directly into the workspace ---
        (workspace / "gate.py").write_text("import sys; sys.exit(0)\n")

        gate_result = await GateRunner(backend).run(workspace, ["python gate.py"])
        assert gate_result.passed is True, f"gate failures: {gate_result.failures}"
    finally:
        await backend.cleanup_workspace(workspace)
        assert not workspace.exists()
