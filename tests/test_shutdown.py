"""Tests for shutdown cleanup, limiter behavior, and sandbox path safety."""

from __future__ import annotations

from pathlib import Path

import pytest

from gradex.backends.base import GradexSecurityError
from gradex.backends.worktree import WorktreeBackend


@pytest.fixture(autouse=True)
def patch_gradex_dir(git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect state/worktree directories into temporary repository."""
    gradex_dir = git_repo / ".gradex"
    monkeypatch.setattr("gradex.state.GRADEX_DIR", gradex_dir)
    monkeypatch.setattr("gradex.backends.worktree.GRADEX_DIR", gradex_dir)


@pytest.mark.anyio
async def test_cleanup_all_sync_cleans_worktrees(git_repo: Path) -> None:
    backend = WorktreeBackend(repo_root=git_repo)
    ws1 = await backend.create_workspace("sd1-test-1")
    ws2 = await backend.create_workspace("sd2-test-2")
    assert ws1.exists() and ws2.exists()
    backend._cleanup_all_sync()
    assert not ws1.exists()
    assert not ws2.exists()


@pytest.mark.anyio
async def test_cleanup_all_sync_idempotent(git_repo: Path) -> None:
    backend = WorktreeBackend(repo_root=git_repo)
    _ = await backend.create_workspace("sd3-test-3")
    backend._cleanup_all_sync()
    backend._cleanup_all_sync()


def test_rate_limiter_allows_immediate_on_fresh_bucket() -> None:
    from gradex.ai.client import _TokenBucket

    bucket = _TokenBucket(max_requests=10)
    wait = bucket.consume()
    assert wait == 0.0


def test_rate_limiter_throttles_after_exhaustion() -> None:
    from gradex.ai.client import _TokenBucket

    bucket = _TokenBucket(max_requests=2)
    bucket.consume()
    bucket.consume()
    wait = bucket.consume()
    assert wait > 0.0


@pytest.mark.anyio
async def test_path_safety_allows_workspace_write(git_repo: Path) -> None:
    backend = WorktreeBackend(repo_root=git_repo)
    workspace = await backend.create_workspace("safety-test-1")
    try:
        backend._assert_safe_path(workspace / "src" / "file.py", workspace)
    finally:
        await backend.cleanup_workspace(workspace)


@pytest.mark.anyio
async def test_path_safety_blocks_escape(git_repo: Path) -> None:
    backend = WorktreeBackend(repo_root=git_repo)
    workspace = await backend.create_workspace("safety-test-2")
    try:
        with pytest.raises(GradexSecurityError):
            backend._assert_safe_path(Path("/etc/passwd"), workspace)
    finally:
        await backend.cleanup_workspace(workspace)
