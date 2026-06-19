"""Tests for the host plugin installer system."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from gradex.hosts import SUPPORTED_HOSTS, get_installer
from gradex.hosts.claude_code import ClaudeCodeInstaller
from gradex.hosts.cursor import CursorInstaller

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_claude_skills(tmp_path: Path) -> Path:
    """Create minimal skill files for ClaudeCodeInstaller tests."""
    src = tmp_path / "skills" / "claude-code"
    (src / "discover").mkdir(parents=True)
    (src / "discover" / "SKILL.md").write_text("# Discover skill", encoding="utf-8")
    (src / "optimize").mkdir(parents=True)
    (src / "optimize" / "SKILL.md").write_text("# Optimize skill", encoding="utf-8")
    return src


def _make_cursor_skills(tmp_path: Path) -> Path:
    """Create minimal skill files for CursorInstaller tests."""
    src = tmp_path / "skills" / "cursor"
    src.mkdir(parents=True)
    (src / "discover.mdc").write_text("# discover mdc", encoding="utf-8")
    (src / "optimize.mdc").write_text("# optimize mdc", encoding="utf-8")
    return src


# ---------------------------------------------------------------------------
# ClaudeCodeInstaller
# ---------------------------------------------------------------------------


class TestClaudeCodeInstaller:
    def test_install_creates_plugin_json(self, tmp_path: Path) -> None:
        """install() writes plugin.json with the expected structure."""
        plugin_dir = tmp_path / "plugin"
        skills_src = _make_claude_skills(tmp_path)
        installer = ClaudeCodeInstaller(plugin_dir=plugin_dir, skills_source=skills_src)

        result = installer.install()

        assert result.success
        manifest_path = plugin_dir / "plugin.json"
        assert manifest_path.exists()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["name"] == "evo"
        assert len(manifest["skills"]) == 2

    def test_install_copies_skill_files(self, tmp_path: Path) -> None:
        """install() copies both SKILL.md files to the plugin directory."""
        plugin_dir = tmp_path / "plugin"
        skills_src = _make_claude_skills(tmp_path)
        installer = ClaudeCodeInstaller(plugin_dir=plugin_dir, skills_source=skills_src)

        result = installer.install()

        assert result.success
        assert (plugin_dir / "discover" / "SKILL.md").exists()
        assert (plugin_dir / "optimize" / "SKILL.md").exists()
        assert "discover/SKILL.md" in result.files_written
        assert "optimize/SKILL.md" in result.files_written

    def test_install_is_idempotent(self, tmp_path: Path) -> None:
        """Calling install() twice does not raise and still succeeds."""
        plugin_dir = tmp_path / "plugin"
        skills_src = _make_claude_skills(tmp_path)
        installer = ClaudeCodeInstaller(plugin_dir=plugin_dir, skills_source=skills_src)

        r1 = installer.install()
        r2 = installer.install()

        assert r1.success
        assert r2.success

    def test_install_fails_gracefully_on_missing_source(self, tmp_path: Path) -> None:
        """install() returns success=False when the skills source does not exist."""
        plugin_dir = tmp_path / "plugin"
        installer = ClaudeCodeInstaller(
            plugin_dir=plugin_dir,
            skills_source=tmp_path / "nonexistent",
        )
        result = installer.install()

        assert not result.success
        assert result.message  # error message is populated

    def test_is_installed_false_initially(self, tmp_path: Path) -> None:
        """is_installed() is False when the plugin directory does not exist."""
        installer = ClaudeCodeInstaller(
            plugin_dir=tmp_path / "missing",
            skills_source=_make_claude_skills(tmp_path),
        )
        assert not installer.is_installed()

    def test_is_installed_true_after_install(self, tmp_path: Path) -> None:
        """is_installed() returns True once install() has completed."""
        plugin_dir = tmp_path / "plugin"
        skills_src = _make_claude_skills(tmp_path)
        installer = ClaudeCodeInstaller(plugin_dir=plugin_dir, skills_source=skills_src)
        installer.install()

        assert installer.is_installed()

    def test_doctor_clean_after_full_install(self, tmp_path: Path) -> None:
        """doctor() has no errors after a successful install (with mocked binaries)."""
        plugin_dir = tmp_path / "plugin"
        skills_src = _make_claude_skills(tmp_path)
        installer = ClaudeCodeInstaller(plugin_dir=plugin_dir, skills_source=skills_src)
        installer.install()

        with patch(
            "gradex.hosts.claude_code.shutil.which", return_value="/usr/bin/mock"
        ):
            issues = installer.doctor()

        errors = [i for i in issues if i.severity == "error"]
        assert errors == [], f"Unexpected errors: {errors}"

    def test_doctor_error_missing_claude_binary(self, tmp_path: Path) -> None:
        """doctor() returns an error when the 'claude' binary is absent."""
        plugin_dir = tmp_path / "plugin"
        skills_src = _make_claude_skills(tmp_path)
        installer = ClaudeCodeInstaller(plugin_dir=plugin_dir, skills_source=skills_src)
        installer.install()

        def _which(name: str) -> str | None:
            return None if name == "claude" else "/usr/bin/mock"

        with patch("gradex.hosts.claude_code.shutil.which", side_effect=_which):
            issues = installer.doctor()

        messages = [i.message for i in issues if i.severity == "error"]
        assert any("Claude Code CLI" in m for m in messages)

    def test_doctor_error_missing_plugin_dir(self, tmp_path: Path) -> None:
        """doctor() returns an error when the plugin directory is absent."""
        installer = ClaudeCodeInstaller(
            plugin_dir=tmp_path / "missing_dir",
            skills_source=_make_claude_skills(tmp_path),
        )
        with patch("gradex.hosts.claude_code.shutil.which", return_value="/bin/mock"):
            issues = installer.doctor()

        messages = [i.message for i in issues if i.severity == "error"]
        assert any("Plugin dir" in m for m in messages)

    def test_doctor_error_missing_skill_files(self, tmp_path: Path) -> None:
        """doctor() returns errors when skill files are absent."""
        plugin_dir = tmp_path / "plugin"
        plugin_dir.mkdir(parents=True)
        # Write manifest but no skill files
        (plugin_dir / "plugin.json").write_text('{"name":"evo"}', encoding="utf-8")

        installer = ClaudeCodeInstaller(
            plugin_dir=plugin_dir,
            skills_source=_make_claude_skills(tmp_path),
        )
        with patch("gradex.hosts.claude_code.shutil.which", return_value="/bin/mock"):
            issues = installer.doctor()

        messages = [i.message for i in issues if i.severity == "error"]
        assert any("discover" in m for m in messages)
        assert any("optimize" in m for m in messages)

    def test_doctor_warning_missing_evo_binary(self, tmp_path: Path) -> None:
        """doctor() emits a warning when 'evo' is not on PATH."""
        plugin_dir = tmp_path / "plugin"
        installer = ClaudeCodeInstaller(
            plugin_dir=plugin_dir,
            skills_source=_make_claude_skills(tmp_path),
        )
        installer.install()

        def _which(name: str) -> str | None:
            return None if name == "evo" else "/usr/bin/mock"

        with patch("gradex.hosts.claude_code.shutil.which", side_effect=_which):
            issues = installer.doctor()

        warnings = [i for i in issues if i.severity == "warning"]
        assert any("evo" in i.message for i in warnings)

    def test_doctor_warning_invalid_manifest_json(self, tmp_path: Path) -> None:
        """doctor() emits a warning when plugin.json contains invalid JSON."""
        plugin_dir = tmp_path / "plugin"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "plugin.json").write_text("NOT JSON", encoding="utf-8")

        installer = ClaudeCodeInstaller(
            plugin_dir=plugin_dir,
            skills_source=_make_claude_skills(tmp_path),
        )
        with patch("gradex.hosts.claude_code.shutil.which", return_value="/bin/mock"):
            issues = installer.doctor()

        warnings = [i for i in issues if i.severity == "warning"]
        assert any("JSON" in i.message for i in warnings)


# ---------------------------------------------------------------------------
# CursorInstaller
# ---------------------------------------------------------------------------


class TestCursorInstaller:
    def test_install_creates_cursor_rules(self, tmp_path: Path) -> None:
        """install() creates .cursor/rules/ and writes both .mdc files."""
        project_root = tmp_path / "project"
        project_root.mkdir()
        skills_src = _make_cursor_skills(tmp_path)
        installer = CursorInstaller(project_root=project_root, skills_source=skills_src)

        result = installer.install()

        assert result.success
        rules_dir = project_root / ".cursor" / "rules"
        assert (rules_dir / "evo-discover.mdc").exists()
        assert (rules_dir / "evo-optimize.mdc").exists()
        assert "evo-discover.mdc" in result.files_written
        assert "evo-optimize.mdc" in result.files_written

    def test_install_plugin_dir_property(self, tmp_path: Path) -> None:
        """plugin_dir returns <project_root>/.cursor/rules/."""
        project_root = tmp_path / "project"
        project_root.mkdir()
        installer = CursorInstaller(
            project_root=project_root,
            skills_source=_make_cursor_skills(tmp_path),
        )
        assert installer.plugin_dir == project_root / ".cursor" / "rules"

    def test_install_is_idempotent(self, tmp_path: Path) -> None:
        """Calling install() twice still succeeds."""
        project_root = tmp_path / "project"
        project_root.mkdir()
        skills_src = _make_cursor_skills(tmp_path)
        installer = CursorInstaller(project_root=project_root, skills_source=skills_src)

        assert installer.install().success
        assert installer.install().success

    def test_install_fails_gracefully_on_missing_source(self, tmp_path: Path) -> None:
        """install() returns success=False when the skills source does not exist."""
        project_root = tmp_path / "project"
        project_root.mkdir()
        installer = CursorInstaller(
            project_root=project_root,
            skills_source=tmp_path / "nonexistent",
        )
        result = installer.install()

        assert not result.success
        assert result.message

    def test_is_installed_false_initially(self, tmp_path: Path) -> None:
        """is_installed() is False before install()."""
        project_root = tmp_path / "project"
        project_root.mkdir()
        installer = CursorInstaller(
            project_root=project_root,
            skills_source=_make_cursor_skills(tmp_path),
        )
        assert not installer.is_installed()

    def test_is_installed_true_after_install(self, tmp_path: Path) -> None:
        """is_installed() is True after a successful install()."""
        project_root = tmp_path / "project"
        project_root.mkdir()
        skills_src = _make_cursor_skills(tmp_path)
        installer = CursorInstaller(project_root=project_root, skills_source=skills_src)
        installer.install()

        assert installer.is_installed()

    def test_doctor_clean_after_install(self, tmp_path: Path) -> None:
        """doctor() has no errors after install (with mocked cursor binary)."""
        project_root = tmp_path / "project"
        project_root.mkdir()
        installer = CursorInstaller(
            project_root=project_root,
            skills_source=_make_cursor_skills(tmp_path),
        )
        installer.install()

        with patch("gradex.hosts.cursor.shutil.which", return_value="/usr/bin/cursor"):
            issues = installer.doctor()

        errors = [i for i in issues if i.severity == "error"]
        assert errors == [], f"Unexpected errors: {errors}"

    def test_doctor_error_missing_rules_dir(self, tmp_path: Path) -> None:
        """doctor() reports an error when .cursor/rules/ does not exist."""
        project_root = tmp_path / "project"
        project_root.mkdir()
        installer = CursorInstaller(
            project_root=project_root,
            skills_source=_make_cursor_skills(tmp_path),
        )
        with patch("gradex.hosts.cursor.shutil.which", return_value="/bin/cursor"):
            issues = installer.doctor()

        messages = [i.message for i in issues if i.severity == "error"]
        assert any(".cursor/rules" in m for m in messages)

    def test_doctor_error_missing_mdc_files(self, tmp_path: Path) -> None:
        """doctor() reports errors when .mdc files are absent."""
        project_root = tmp_path / "project"
        rules_dir = project_root / ".cursor" / "rules"
        rules_dir.mkdir(parents=True)
        installer = CursorInstaller(
            project_root=project_root,
            skills_source=_make_cursor_skills(tmp_path),
        )
        with patch("gradex.hosts.cursor.shutil.which", return_value="/bin/cursor"):
            issues = installer.doctor()

        messages = [i.message for i in issues if i.severity == "error"]
        assert any("discover" in m for m in messages)
        assert any("optimize" in m for m in messages)

    def test_doctor_warning_missing_cursor_binary(self, tmp_path: Path) -> None:
        """doctor() emits a warning when 'cursor' is not on PATH."""
        project_root = tmp_path / "project"
        project_root.mkdir()
        installer = CursorInstaller(
            project_root=project_root,
            skills_source=_make_cursor_skills(tmp_path),
        )
        installer.install()

        with patch("gradex.hosts.cursor.shutil.which", return_value=None):
            issues = installer.doctor()

        warnings = [i for i in issues if i.severity == "warning"]
        assert any("cursor" in i.message.lower() for i in warnings)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_get_installer_claude_code() -> None:
    """get_installer('claude-code') returns a ClaudeCodeInstaller."""
    installer = get_installer("claude-code")
    assert isinstance(installer, ClaudeCodeInstaller)
    assert installer.host_name == "claude-code"


def test_get_installer_cursor() -> None:
    """get_installer('cursor') returns a CursorInstaller."""
    installer = get_installer("cursor")
    assert isinstance(installer, CursorInstaller)
    assert installer.host_name == "cursor"


def test_get_installer_unknown_raises() -> None:
    """get_installer() raises ValueError for an unknown host."""
    with pytest.raises(ValueError, match="no-such-host"):
        get_installer("no-such-host")


def test_supported_hosts_contains_both() -> None:
    """SUPPORTED_HOSTS lists both claude-code and cursor."""
    assert "claude-code" in SUPPORTED_HOSTS
    assert "cursor" in SUPPORTED_HOSTS


def test_installer_host_name_matches_registry_key() -> None:
    """Each installer's host_name matches its registry key."""
    for key in SUPPORTED_HOSTS:
        installer = get_installer(key)
        assert installer.host_name == key
