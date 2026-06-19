"""Claude Code host installer."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from gradex.hosts.base import DoctorIssue, HostInstaller, InstallResult

# Source skill files bundled with the evo package (repo root / skills / claude-code)
SKILLS_SOURCE: Path = (
    Path(__file__).parent.parent.parent.parent / "skills" / "claude-code"
)

# Default installation target: ~/.claude/plugins/evo/
PLUGIN_DIR: Path = Path.home() / ".claude" / "plugins" / "gradex"

_MANIFEST: dict[str, object] = {
    "name": "evo",
    "version": "0.1.0",
    "description": "Autoresearch orchestrator — measurable code improvement",
    "skills": [
        {"name": "discover", "path": "discover/SKILL.md"},
        {"name": "optimize", "path": "optimize/SKILL.md"},
    ],
}


class ClaudeCodeInstaller(HostInstaller):
    """Installs evo skill files into ``~/.claude/plugins/evo/``."""

    def __init__(
        self,
        plugin_dir: Path | None = None,
        skills_source: Path | None = None,
    ) -> None:
        self._plugin_dir = plugin_dir if plugin_dir is not None else PLUGIN_DIR
        self._skills_source = (
            skills_source if skills_source is not None else SKILLS_SOURCE
        )

    @property
    def host_name(self) -> str:
        return "claude-code"

    @property
    def display_name(self) -> str:
        return "Claude Code"

    def install(self) -> InstallResult:
        """Create plugin directory and copy skill files. Idempotent. Never raises."""
        files_written: list[str] = []
        try:
            # 1. Create plugin directory
            self._plugin_dir.mkdir(parents=True, exist_ok=True)

            # 2. Write plugin.json manifest
            self._write_manifest()
            files_written.append("plugin.json")

            # 3. Copy discover/SKILL.md
            discover_src = self._skills_source / "discover" / "SKILL.md"
            discover_dst = self._plugin_dir / "discover" / "SKILL.md"
            discover_dst.parent.mkdir(parents=True, exist_ok=True)
            discover_dst.write_text(
                discover_src.read_text(encoding="utf-8"), encoding="utf-8"
            )
            files_written.append("discover/SKILL.md")

            # 4. Copy optimize/SKILL.md
            optimize_src = self._skills_source / "optimize" / "SKILL.md"
            optimize_dst = self._plugin_dir / "optimize" / "SKILL.md"
            optimize_dst.parent.mkdir(parents=True, exist_ok=True)
            optimize_dst.write_text(
                optimize_src.read_text(encoding="utf-8"), encoding="utf-8"
            )
            files_written.append("optimize/SKILL.md")

            return InstallResult(
                success=True,
                host=self.host_name,
                plugin_dir=self._plugin_dir,
                files_written=files_written,
            )
        except OSError as exc:
            return InstallResult(
                success=False,
                host=self.host_name,
                plugin_dir=self._plugin_dir,
                files_written=files_written,
                message=str(exc),
            )

    def _write_manifest(self) -> None:
        """Write ``plugin.json`` into the plugin directory."""
        manifest_path = self._plugin_dir / "plugin.json"
        manifest_path.write_text(json.dumps(_MANIFEST, indent=2), encoding="utf-8")

    def doctor(self) -> list[DoctorIssue]:
        """Return every environment issue found for Claude Code."""
        issues: list[DoctorIssue] = []

        # 1. claude binary
        if not shutil.which("claude"):
            issues.append(
                DoctorIssue(
                    severity="error",
                    message="Claude Code CLI not found",
                    fix="npm install -g @anthropic-ai/claude-code",
                )
            )

        # 2. Plugin directory
        if not self._plugin_dir.exists():
            issues.append(
                DoctorIssue(
                    severity="error",
                    message=f"Plugin dir not found: {self._plugin_dir}",
                    fix="gradex install claude-code",
                )
            )
        else:
            # 3. plugin.json
            manifest_path = self._plugin_dir / "plugin.json"
            if not manifest_path.exists():
                issues.append(
                    DoctorIssue(
                        severity="error",
                        message="plugin.json not found",
                        fix="gradex install claude-code",
                    )
                )
            else:
                try:
                    json.loads(manifest_path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    issues.append(
                        DoctorIssue(
                            severity="warning",
                            message="plugin.json is not valid JSON",
                            fix="gradex install claude-code",
                        )
                    )

            # 4. discover/SKILL.md
            discover_path = self._plugin_dir / "discover" / "SKILL.md"
            if not discover_path.exists() or discover_path.stat().st_size == 0:
                issues.append(
                    DoctorIssue(
                        severity="error",
                        message="discover/SKILL.md missing or empty",
                        fix="gradex install claude-code",
                    )
                )

            # 5. optimize/SKILL.md
            optimize_path = self._plugin_dir / "optimize" / "SKILL.md"
            if not optimize_path.exists() or optimize_path.stat().st_size == 0:
                issues.append(
                    DoctorIssue(
                        severity="error",
                        message="optimize/SKILL.md missing or empty",
                        fix="gradex install claude-code",
                    )
                )

        # 6. evo binary
        if not shutil.which("evo"):
            issues.append(
                DoctorIssue(
                    severity="warning",
                    message="evo not on PATH (dev install?)",
                    fix="pip install -e .",
                )
            )

        return issues

    def is_installed(self) -> bool:
        """Return ``True`` when both skill files are present and non-empty."""
        discover = self._plugin_dir / "discover" / "SKILL.md"
        optimize_p = self._plugin_dir / "optimize" / "SKILL.md"
        return (
            discover.exists()
            and discover.stat().st_size > 0
            and optimize_p.exists()
            and optimize_p.stat().st_size > 0
        )
