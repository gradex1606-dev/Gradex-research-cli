"""Cursor host installer — installs per-project .mdc rule files."""

from __future__ import annotations

import shutil
from pathlib import Path

from gradex.hosts.base import DoctorIssue, HostInstaller, InstallResult

# Source .mdc files bundled with the evo package (repo root / skills / cursor)
SKILLS_SOURCE: Path = Path(__file__).parent.parent.parent.parent / "skills" / "cursor"


class CursorInstaller(HostInstaller):
    """Installs evo rule files into ``<project>/.cursor/rules/``.

    Cursor's plugin model is per-project: users run ``gradex install cursor``
    from their repo root and evo writes ``.mdc`` files that Cursor picks up
    automatically.
    """

    def __init__(
        self,
        project_root: Path | None = None,
        skills_source: Path | None = None,
    ) -> None:
        self._project_root = project_root if project_root is not None else Path.cwd()
        self._skills_source = (
            skills_source if skills_source is not None else SKILLS_SOURCE
        )

    @property
    def plugin_dir(self) -> Path:
        """Absolute path to ``.cursor/rules/`` inside the project root."""
        return self._project_root / ".cursor" / "rules"

    @property
    def host_name(self) -> str:
        return "cursor"

    @property
    def display_name(self) -> str:
        return "Cursor"

    def install(self) -> InstallResult:
        """Create ``.cursor/rules/`` and copy ``.mdc`` files. Idempotent. Never raises."""
        files_written: list[str] = []
        try:
            # 1. Create .cursor/rules/
            self.plugin_dir.mkdir(parents=True, exist_ok=True)

            # 2. Copy discover.mdc
            discover_src = self._skills_source / "discover.mdc"
            discover_dst = self.plugin_dir / "evo-discover.mdc"
            discover_dst.write_text(
                discover_src.read_text(encoding="utf-8"), encoding="utf-8"
            )
            files_written.append("evo-discover.mdc")

            # 3. Copy optimize.mdc
            optimize_src = self._skills_source / "optimize.mdc"
            optimize_dst = self.plugin_dir / "evo-optimize.mdc"
            optimize_dst.write_text(
                optimize_src.read_text(encoding="utf-8"), encoding="utf-8"
            )
            files_written.append("evo-optimize.mdc")

            return InstallResult(
                success=True,
                host=self.host_name,
                plugin_dir=self.plugin_dir,
                files_written=files_written,
            )
        except OSError as exc:
            return InstallResult(
                success=False,
                host=self.host_name,
                plugin_dir=self.plugin_dir,
                files_written=files_written,
                message=str(exc),
            )

    def doctor(self) -> list[DoctorIssue]:
        """Return every environment issue found for Cursor."""
        issues: list[DoctorIssue] = []

        # 1. .cursor/rules/ directory
        if not self.plugin_dir.exists():
            issues.append(
                DoctorIssue(
                    severity="error",
                    message=".cursor/rules/ not found in project",
                    fix="gradex install cursor",
                )
            )
        else:
            # 2. evo-discover.mdc
            discover_path = self.plugin_dir / "evo-discover.mdc"
            if not discover_path.exists() or discover_path.stat().st_size == 0:
                issues.append(
                    DoctorIssue(
                        severity="error",
                        message="evo-discover.mdc missing or empty",
                        fix="gradex install cursor",
                    )
                )

            # 3. evo-optimize.mdc
            optimize_path = self.plugin_dir / "evo-optimize.mdc"
            if not optimize_path.exists() or optimize_path.stat().st_size == 0:
                issues.append(
                    DoctorIssue(
                        severity="error",
                        message="evo-optimize.mdc missing or empty",
                        fix="gradex install cursor",
                    )
                )

        # 4. cursor binary (warning only — app install is common)
        if not shutil.which("cursor"):
            issues.append(
                DoctorIssue(
                    severity="warning",
                    message="cursor CLI not found (Cursor may be installed as app only)",
                    fix="Install Cursor CLI or open Cursor IDE directly",
                )
            )

        return issues

    def is_installed(self) -> bool:
        """Return ``True`` when both rule files are present and non-empty."""
        discover = self.plugin_dir / "evo-discover.mdc"
        optimize_p = self.plugin_dir / "evo-optimize.mdc"
        return (
            discover.exists()
            and discover.stat().st_size > 0
            and optimize_p.exists()
            and optimize_p.stat().st_size > 0
        )
