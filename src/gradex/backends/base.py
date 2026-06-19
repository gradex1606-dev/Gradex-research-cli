"""Abstract execution backend and shared result types."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CommandResult:
    """The outcome of running a command inside a backend workspace."""

    stdout: str
    stderr: str
    exit_code: int
    duration_ms: int
    timed_out: bool = False


class Backend(ABC):
    """Abstract execution backend.

    Concrete subclasses provide workspace isolation strategies (e.g. git
    worktrees, Docker containers, plain directories).
    """

    @abstractmethod
    async def create_workspace(self, experiment_id: str) -> Path:
        """Create an isolated workspace for *experiment_id*.

        Returns the absolute path to the new workspace directory.
        """

    @abstractmethod
    async def run_command(
        self,
        workspace_path: Path,
        cmd: list[str],
        timeout: int = 120,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        """Execute *cmd* inside *workspace_path* and return the result."""

    @abstractmethod
    async def cleanup_workspace(self, workspace_path: Path) -> None:
        """Destroy the workspace at *workspace_path*.

        Must not raise even if the workspace no longer exists (idempotent).
        """

    @abstractmethod
    def list_workspaces(self) -> list[Path]:
        """Return every workspace path currently tracked by this backend."""


# ---------------------------------------------------------------------------
# Error hierarchy
# ---------------------------------------------------------------------------


class GradexBackendError(Exception):
    """Base error for all backend failures."""


class GradexWorktreeError(GradexBackendError):
    """A git worktree operation failed."""


class GradexTimeoutError(GradexBackendError):
    """A command exceeded its time limit."""


class GradexSecurityError(GradexBackendError):
    """Attempted file write outside sandbox."""
