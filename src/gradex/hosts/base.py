"""Abstract base classes for host plugin installers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class InstallResult:
    """The outcome of a plugin installation attempt."""

    success: bool
    host: str
    plugin_dir: Path
    files_written: list[str] = field(default_factory=list)
    message: str = ""


@dataclass
class DoctorIssue:
    """A single issue found by a doctor check."""

    severity: str  # "error" | "warning"
    message: str
    fix: str


class HostInstaller(ABC):
    """Abstract base class for host-specific plugin installers.

    Each concrete subclass handles one coding host (Claude Code, Cursor, …).
    All public methods are **idempotent** and **never raise** — errors are
    returned as :class:`InstallResult` or :class:`DoctorIssue` objects.
    """

    @property
    @abstractmethod
    def host_name(self) -> str:
        """Short identifier used in CLI commands (e.g. ``"claude-code"``)."""

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name for output (e.g. ``"Claude Code"``)."""

    @abstractmethod
    def install(self) -> InstallResult:
        """Idempotent installation.

        Copies plugin/skill files to the appropriate location.
        Returns :class:`InstallResult` with ``success=False`` on any error.
        Never raises.
        """

    @abstractmethod
    def doctor(self) -> list[DoctorIssue]:
        """Run all environment checks for this host.

        Returns every :class:`DoctorIssue` found.
        An empty list means everything is healthy.
        """

    @abstractmethod
    def is_installed(self) -> bool:
        """Return ``True`` if the plugin files appear to be present."""
