"""Tests for the doctor environment checks."""

from __future__ import annotations

import sys
from collections import namedtuple
from unittest.mock import MagicMock, patch

from gradex.doctor import (
    CheckResult,
    check_git,
    check_host_cli,
    check_python_version,
    print_results,
    run_doctor,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# A named tuple compatible with sys.version_info (supports tuple comparison).
_VersionInfo = namedtuple(
    "_VersionInfo", ["major", "minor", "micro", "releaselevel", "serial"]
)


def _vi(major: int, minor: int, micro: int = 0) -> _VersionInfo:
    return _VersionInfo(major, minor, micro, "final", 0)


# ---------------------------------------------------------------------------
# check_git
# ---------------------------------------------------------------------------


def test_check_git_found() -> None:
    """check_git passes when git is on PATH and returns a version string."""
    mock_proc = MagicMock()
    mock_proc.stdout = "git version 2.44.0"
    with patch("gradex.doctor.shutil.which", return_value="/usr/bin/git"):
        with patch("gradex.doctor.subprocess.run", return_value=mock_proc):
            result = check_git()
    assert result.passed is True
    assert "git version" in result.message


def test_check_git_not_found() -> None:
    """check_git fails when git is absent from PATH."""
    with patch("gradex.doctor.shutil.which", return_value=None):
        result = check_git()
    assert result.passed is False
    assert "not found" in result.message


def test_check_git_timeout() -> None:
    """check_git fails gracefully when git --version times out."""
    import subprocess

    with patch("gradex.doctor.shutil.which", return_value="/usr/bin/git"):
        with patch(
            "gradex.doctor.subprocess.run",
            side_effect=subprocess.TimeoutExpired("git", 5),
        ):
            result = check_git()
    assert result.passed is False
    assert "timed out" in result.message


def test_check_git_oserror() -> None:
    """check_git fails gracefully on OSError."""
    with patch("gradex.doctor.shutil.which", return_value="/usr/bin/git"):
        with patch(
            "gradex.doctor.subprocess.run", side_effect=OSError("permission denied")
        ):
            result = check_git()
    assert result.passed is False
    assert "Error" in result.message


# ---------------------------------------------------------------------------
# check_python_version
# ---------------------------------------------------------------------------


def test_check_python_version_311_passes() -> None:
    """check_python_version passes on Python 3.11."""
    with patch.object(sys, "version_info", _vi(3, 11)):
        result = check_python_version()
    assert result.passed is True


def test_check_python_version_312_passes() -> None:
    """check_python_version passes on Python 3.12."""
    with patch.object(sys, "version_info", _vi(3, 12)):
        result = check_python_version()
    assert result.passed is True


def test_check_python_version_310_fails() -> None:
    """check_python_version fails on Python 3.10."""
    with patch.object(sys, "version_info", _vi(3, 10)):
        result = check_python_version()
    assert result.passed is False
    assert "requires" in result.message


def test_check_python_version_27_fails() -> None:
    """check_python_version fails on Python 2.7."""
    with patch.object(sys, "version_info", _vi(2, 7)):
        result = check_python_version()
    assert result.passed is False


# ---------------------------------------------------------------------------
# check_host_cli
# ---------------------------------------------------------------------------


def test_check_host_cli_unknown_host() -> None:
    """check_host_cli fails immediately for an unknown host."""
    result = check_host_cli("no-such-host")
    assert result.passed is False
    assert "Unknown host" in result.message


def test_check_host_cli_claude_found() -> None:
    """check_host_cli passes when the claude binary is on PATH."""
    with patch("gradex.doctor.shutil.which", return_value="/usr/local/bin/claude"):
        result = check_host_cli("claude-code")
    assert result.passed is True
    assert "claude" in result.message


def test_check_host_cli_claude_not_found() -> None:
    """check_host_cli fails when the claude binary is missing from PATH."""
    with patch("gradex.doctor.shutil.which", return_value=None):
        result = check_host_cli("claude-code")
    assert result.passed is False


def test_check_host_cli_cursor_found() -> None:
    """check_host_cli passes for the cursor host."""
    with patch("gradex.doctor.shutil.which", return_value="/usr/bin/cursor"):
        result = check_host_cli("cursor")
    assert result.passed is True


def test_check_host_cli_copilot_found() -> None:
    """check_host_cli passes for the copilot host (uses gh binary)."""
    with patch("gradex.doctor.shutil.which", return_value="/usr/bin/gh"):
        result = check_host_cli("copilot")
    assert result.passed is True


# ---------------------------------------------------------------------------
# run_doctor
# ---------------------------------------------------------------------------


def test_run_doctor_returns_three_checks() -> None:
    """run_doctor returns exactly three CheckResult items."""
    results = run_doctor("claude-code")
    assert len(results) == 3
    assert all(isinstance(r, CheckResult) for r in results)


# ---------------------------------------------------------------------------
# print_results
# ---------------------------------------------------------------------------


def test_print_results_all_pass_returns_true() -> None:
    """print_results returns True when every check passed."""
    results = [
        CheckResult(name="foo", passed=True, message="ok"),
        CheckResult(name="bar", passed=True, message="ok"),
    ]
    assert print_results(results) is True


def test_print_results_any_fail_returns_false() -> None:
    """print_results returns False when at least one check failed."""
    results = [
        CheckResult(name="foo", passed=True, message="ok"),
        CheckResult(name="bar", passed=False, message="missing"),
    ]
    assert print_results(results) is False
