"""Host plugin installer registry."""

from __future__ import annotations

from gradex.hosts.base import DoctorIssue, HostInstaller, InstallResult
from gradex.hosts.claude_code import ClaudeCodeInstaller
from gradex.hosts.cursor import CursorInstaller

__all__ = [
    "ClaudeCodeInstaller",
    "CursorInstaller",
    "DoctorIssue",
    "HostInstaller",
    "InstallResult",
    "REGISTRY",
    "SUPPORTED_HOSTS",
    "get_installer",
]

REGISTRY: dict[str, type[HostInstaller]] = {
    "claude-code": ClaudeCodeInstaller,
    "cursor": CursorInstaller,
}

SUPPORTED_HOSTS: list[str] = list(REGISTRY.keys())


def get_installer(host: str) -> HostInstaller:
    """Return a :class:`HostInstaller` for *host*.

    Args:
        host: Short host name, e.g. ``"claude-code"`` or ``"cursor"``.

    Raises:
        ValueError: If *host* is not in the registry.
    """
    if host not in REGISTRY:
        supported = ", ".join(SUPPORTED_HOSTS)
        raise ValueError(f"Unknown host: {host!r}. Supported: {supported}")
    return REGISTRY[host]()
