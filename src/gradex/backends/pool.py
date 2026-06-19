"""Async worktree pool for bounded workspace reuse."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from gradex.backends.base import Backend

logger = logging.getLogger(__name__)


class WorktreePool:
    """Pool of pre-created worktrees.

    Workspaces are initialized up front, then claimed/released through an async
    context manager. On release, each workspace is reset to a clean git state.
    """

    def __init__(self, backend: Backend, pool_size: int = 3) -> None:
        self._backend = backend
        self._pool_size = pool_size
        self._available: asyncio.Queue[Path] = asyncio.Queue()
        self._all_workspaces: list[Path] = []

    async def initialize(self, run_id: str) -> None:
        """Pre-create ``pool_size`` worktrees concurrently."""
        tasks = [
            self._backend.create_workspace(f"p{i:02d}-{run_id}-pool-{i}")
            for i in range(self._pool_size)
        ]
        workspaces = await asyncio.gather(*tasks)
        for workspace in workspaces:
            self._all_workspaces.append(workspace)
            await self._available.put(workspace)

    def claim(self) -> PooledWorkspace:
        """Return an async context manager that claims one workspace."""
        return PooledWorkspace(self)

    async def _acquire(self) -> Path:
        return await self._available.get()

    async def _release(self, workspace: Path) -> None:
        """Reset and return workspace to the queue; discard on reset failure."""
        checkout = await self._backend.run_command(
            workspace, ["git", "checkout", "."], timeout=30
        )
        clean = await self._backend.run_command(
            workspace, ["git", "clean", "-fd"], timeout=30
        )

        if checkout.exit_code == 0 and clean.exit_code == 0:
            await self._available.put(workspace)
            return

        logger.warning("Discarding dirty workspace after reset failure: %s", workspace)
        try:
            await self._backend.cleanup_workspace(workspace)
        except Exception:  # noqa: BLE001
            logger.warning("Failed to cleanup discarded workspace: %s", workspace)

        if workspace in self._all_workspaces:
            self._all_workspaces.remove(workspace)

    async def shutdown(self) -> None:
        """Best-effort cleanup of all known workspaces; never raises."""
        for workspace in list(self._all_workspaces):
            try:
                await self._backend.cleanup_workspace(workspace)
            except Exception:  # noqa: BLE001
                continue
        self._all_workspaces.clear()
        while not self._available.empty():
            try:
                self._available.get_nowait()
            except asyncio.QueueEmpty:
                break


class PooledWorkspace:
    """Async context manager for claimed pool workspaces."""

    def __init__(self, pool: WorktreePool) -> None:
        self._pool = pool
        self._workspace: Path | None = None

    async def __aenter__(self) -> Path:
        self._workspace = await self._pool._acquire()
        return self._workspace

    async def __aexit__(self, *args: object) -> None:
        if self._workspace is None:
            return
        await self._pool._release(self._workspace)
