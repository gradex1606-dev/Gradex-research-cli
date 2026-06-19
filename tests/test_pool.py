"""Tests for async WorktreePool workspace reuse."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from gradex.backends.pool import WorktreePool
from gradex.backends.worktree import WorktreeBackend


@pytest.fixture(autouse=True)
def patch_gradex_dir(git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep worktree outputs inside each temporary test repository."""
    gradex_dir = git_repo / ".gradex"
    monkeypatch.setattr("gradex.state.GRADEX_DIR", gradex_dir)
    monkeypatch.setattr("gradex.backends.worktree.GRADEX_DIR", gradex_dir)


@pytest.mark.anyio
async def test_pool_initializes_workspaces(git_repo: Path) -> None:
    backend = WorktreeBackend(repo_root=git_repo)
    pool = WorktreePool(backend, pool_size=3)
    await pool.initialize("test-run")
    assert len(pool._all_workspaces) == 3
    created = list(pool._all_workspaces)
    assert all(path.exists() for path in created)
    await pool.shutdown()
    assert all(not path.exists() for path in created)


@pytest.mark.anyio
async def test_pool_claim_and_release(git_repo: Path) -> None:
    backend = WorktreeBackend(repo_root=git_repo)
    pool = WorktreePool(backend, pool_size=1)
    await pool.initialize("test-run-2")
    try:
        async with pool.claim() as workspace:
            assert workspace.exists()
            (workspace / "marker.txt").write_text("test", encoding="utf-8")

        async with pool.claim() as workspace:
            assert not (workspace / "marker.txt").exists()
    finally:
        await pool.shutdown()


@pytest.mark.anyio
async def test_pool_serializes_at_limit(git_repo: Path) -> None:
    backend = WorktreeBackend(repo_root=git_repo)
    pool = WorktreePool(backend, pool_size=1)
    await pool.initialize("test-run-3")
    results: list[int] = []

    async def worker(i: int) -> None:
        async with pool.claim():
            await asyncio.sleep(0.05)
            results.append(i)

    try:
        await asyncio.gather(worker(0), worker(1), worker(2))
        assert len(results) == 3
    finally:
        await pool.shutdown()


@pytest.mark.anyio
async def test_pool_shutdown_cleans_all(git_repo: Path) -> None:
    backend = WorktreeBackend(repo_root=git_repo)
    pool = WorktreePool(backend, pool_size=2)
    await pool.initialize("test-run-clean")
    created = list(pool._all_workspaces)
    await pool.shutdown()
    assert all(not path.exists() for path in created)


@pytest.mark.anyio
async def test_pool_size_respected(git_repo: Path) -> None:
    backend = WorktreeBackend(repo_root=git_repo)
    pool = WorktreePool(backend, pool_size=2)
    await pool.initialize("test-run-4")
    try:
        assert pool._available.qsize() == 2
    finally:
        await pool.shutdown()
