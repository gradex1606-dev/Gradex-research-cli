"""Tests for WorktreeBackend — uses a real git repository."""

from __future__ import annotations

from pathlib import Path

import pytest

from gradex.backends.base import GradexWorktreeError
from gradex.backends.worktree import WorktreeBackend

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def patch_evo_dir(git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect GRADEX_DIR into the test's temporary git repo for isolation."""
    evo_dir = git_repo / ".gradex"
    monkeypatch.setattr("gradex.state.GRADEX_DIR", evo_dir)
    monkeypatch.setattr("gradex.backends.worktree.GRADEX_DIR", evo_dir)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_create_workspace(git_repo: Path) -> None:
    """A new workspace is created as a directory containing repo files."""
    backend = WorktreeBackend(repo_root=git_repo)
    workspace = await backend.create_workspace("test-exp-001")
    try:
        assert workspace.exists()
        assert workspace.is_dir()
        assert (workspace / "hello.py").exists()
    finally:
        await backend.cleanup_workspace(workspace)


@pytest.mark.anyio
async def test_changes_isolated(git_repo: Path) -> None:
    """Writing a file inside a worktree does not affect the main branch."""
    backend = WorktreeBackend(repo_root=git_repo)
    workspace = await backend.create_workspace("test-exp-002")
    try:
        (workspace / "new_file.py").write_text("x = 1\n")
        assert list(git_repo.glob("new_file.py")) == []
    finally:
        await backend.cleanup_workspace(workspace)


@pytest.mark.anyio
async def test_cleanup_removes_worktree(git_repo: Path) -> None:
    """cleanup_workspace removes the worktree directory from disk."""
    backend = WorktreeBackend(repo_root=git_repo)
    workspace = await backend.create_workspace("test-exp-003")
    await backend.cleanup_workspace(workspace)
    assert not workspace.exists()


@pytest.mark.anyio
async def test_cleanup_idempotent(git_repo: Path) -> None:
    """Calling cleanup_workspace twice on the same path must not raise."""
    backend = WorktreeBackend(repo_root=git_repo)
    workspace = await backend.create_workspace("test-exp-004")
    await backend.cleanup_workspace(workspace)
    await backend.cleanup_workspace(workspace)  # second call must be silent


@pytest.mark.anyio
async def test_run_command_success(git_repo: Path) -> None:
    """run_command captures stdout and returns exit_code 0 for a passing command."""
    backend = WorktreeBackend(repo_root=git_repo)
    workspace = await backend.create_workspace("test-exp-005")
    try:
        result = await backend.run_command(workspace, ["python", "-c", "print('42.0')"])
        assert result.exit_code == 0
        assert "42.0" in result.stdout
    finally:
        await backend.cleanup_workspace(workspace)


@pytest.mark.anyio
async def test_run_command_timeout(git_repo: Path) -> None:
    """run_command sets timed_out=True when the process exceeds *timeout*."""
    backend = WorktreeBackend(repo_root=git_repo)
    workspace = await backend.create_workspace("test-exp-006")
    try:
        result = await backend.run_command(
            workspace,
            ["python", "-c", "import time; time.sleep(30)"],
            timeout=1,
        )
        assert result.timed_out is True
    finally:
        await backend.cleanup_workspace(workspace)


@pytest.mark.anyio
async def test_no_git_repo_raises(tmp_path: Path) -> None:
    """create_workspace raises GradexWorktreeError when repo_root is not a git repo."""
    backend = WorktreeBackend(repo_root=tmp_path / "not_a_repo")
    with pytest.raises(GradexWorktreeError):
        await backend.create_workspace("test-exp-007")
