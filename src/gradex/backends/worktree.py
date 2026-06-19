"""Git-worktree-based execution backend for evo experiments."""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import threading
import time
from pathlib import Path

from gradex.backends.base import (
    Backend,
    CommandResult,
    GradexSecurityError,
    GradexWorktreeError,
)

# Module-level name so tests can monkeypatch evo.backends.worktree.GRADEX_DIR
from gradex.state import (
    GRADEX_DIR as GRADEX_DIR,  # re-exported so tests can monkeypatch
)

_repo_git_locks: dict[str, asyncio.Lock] = {}
_repo_git_locks_guard = threading.Lock()


def _git_lock_for(repo_root: Path) -> asyncio.Lock:
    """One asyncio lock per repo — serialises parallel ``git worktree`` calls."""
    key = str(repo_root.resolve())
    with _repo_git_locks_guard:
        if key not in _repo_git_locks:
            _repo_git_locks[key] = asyncio.Lock()
        return _repo_git_locks[key]


class WorktreeBackend(Backend):
    """Execution backend that creates one git worktree per experiment.

    Each instance manages its own ``_workspaces`` dict so there is no shared
    global state between backend instances (e.g. across parallel tests).
    """

    def __init__(self, repo_root: Path | None = None) -> None:
        self._repo_root: Path = repo_root if repo_root is not None else Path.cwd()
        self._workspaces: dict[str, Path] = {}
        self._atexit_registered: bool = False

    # ------------------------------------------------------------------
    # Backend interface
    # ------------------------------------------------------------------

    async def create_workspace(self, experiment_id: str) -> Path:
        """Create a git worktree for *experiment_id* and return its path.

        The worktree is placed at ``GRADEX_DIR / "worktrees" / experiment_id``
        on a freshly-created branch ``evo/<experiment_id[:8]>``.

        Raises:
            GradexWorktreeError: If ``_repo_root`` is not a git repository or
                              if ``git worktree add`` fails.
        """
        if not (self._repo_root / ".git").exists():
            raise GradexWorktreeError(f"Not a git repository: {self._repo_root}")

        # GRADEX_DIR is accessed as a module global so monkeypatching works.
        import gradex.backends.worktree as _self_module

        worktrees_dir = _self_module.GRADEX_DIR / "worktrees"
        worktrees_dir.mkdir(parents=True, exist_ok=True)

        workspace_path = worktrees_dir / experiment_id
        branch = f"gradex/{experiment_id[:8]}"

        async with _git_lock_for(self._repo_root):
            exit_code, _out, stderr = await self._run_git(
                "worktree", "add", str(workspace_path), "-b", branch
            )
        if exit_code != 0:
            raise GradexWorktreeError(
                f"git worktree add failed (exit {exit_code}): {stderr.strip()}"
            )

        self._workspaces[experiment_id] = workspace_path

        if not self._atexit_registered:
            import atexit

            atexit.register(self._cleanup_all_sync)
            self._atexit_registered = True

        return workspace_path

    async def run_command(
        self,
        workspace_path: Path,
        cmd: list[str],
        timeout: int = 120,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        """Run *cmd* in *workspace_path*, enforcing *timeout* seconds.

        On timeout the process is killed, ``process.wait()`` is awaited, and
        a :class:`~evo.backends.base.CommandResult` with ``timed_out=True``
        is returned.  No exception propagates to the caller.

        Uses :func:`asyncio.create_subprocess_exec` (Windows
        ``ProactorEventLoop``-compatible; never ``create_subprocess_shell``).
        """
        self._assert_safe_path(workspace_path, workspace_path)
        start = time.perf_counter()
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=workspace_path,
            env=env,
        )
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(),
                timeout=float(timeout),
            )
            duration_ms = int((time.perf_counter() - start) * 1000)
            return CommandResult(
                stdout=stdout_bytes.decode(errors="replace"),
                stderr=stderr_bytes.decode(errors="replace"),
                exit_code=(process.returncode if process.returncode is not None else 0),
                duration_ms=duration_ms,
                timed_out=False,
            )
        except TimeoutError:
            process.kill()
            # Drain pipes so the OS buffers are released, then wait.
            try:
                await asyncio.wait_for(process.communicate(), timeout=5.0)
            except (TimeoutError, Exception):  # noqa: BLE001
                pass
            await process.wait()
            duration_ms = int((time.perf_counter() - start) * 1000)
            return CommandResult(
                stdout="",
                stderr="",
                exit_code=-1,
                duration_ms=duration_ms,
                timed_out=True,
            )

    def _assert_safe_path(self, path: Path, workspace: Path) -> None:
        """Raise if *path* escapes workspace/GRADEX_DIR."""
        resolved = path.resolve()
        allowed_roots = [workspace.resolve(), GRADEX_DIR.resolve()]
        if not any(resolved.is_relative_to(root) for root in allowed_roots):
            raise GradexSecurityError(f"Path escape attempt: {path} is outside sandbox")

    async def cleanup_workspace(self, workspace_path: Path) -> None:
        """Remove the git worktree at *workspace_path*.

        Logs nothing and never raises; safe to call multiple times.
        """
        async with _git_lock_for(self._repo_root):
            await self._run_git("worktree", "remove", "--force", str(workspace_path))
        # Remove from tracked map regardless of git exit code.
        stale = [k for k, v in self._workspaces.items() if v == workspace_path]
        for key in stale:
            del self._workspaces[key]

    def list_workspaces(self) -> list[Path]:
        """Return all workspace paths currently owned by this backend instance."""
        return list(self._workspaces.values())

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _run_git(self, *args: str) -> tuple[int, str, str]:
        """Run ``git <args>`` from ``_repo_root`` and return (exit_code, stdout, stderr)."""
        process = await asyncio.create_subprocess_exec(
            "git",
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self._repo_root,
        )
        stdout_bytes, stderr_bytes = await process.communicate()
        return (
            process.returncode if process.returncode is not None else 0,
            stdout_bytes.decode(errors="replace"),
            stderr_bytes.decode(errors="replace"),
        )

    def _cleanup_all_sync(self) -> None:
        """atexit handler — synchronous because the event loop may be gone."""
        for path in list(self._workspaces.values()):
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(path)],
                capture_output=True,
                cwd=self._repo_root,
            )
            if path.exists():
                shutil.rmtree(path, ignore_errors=True)
        self._workspaces.clear()
