"""Environment checks for `gradex doctor`."""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass

from rich.console import Console

from gradex.config import HOST_BINARIES, SUPPORTED_HOSTS

console = Console()


@dataclass
class CheckResult:
    """The outcome of a single environment check."""

    name: str
    passed: bool
    message: str


def check_git() -> CheckResult:
    """Check whether git is installed and reachable on PATH.

    Returns a :class:`CheckResult` indicating success or failure,
    including the detected version string on success.
    """
    git_path = shutil.which("git")
    if git_path is None:
        return CheckResult(name="git", passed=False, message="git not found on PATH")

    try:
        proc = subprocess.run(
            ["git", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        version = proc.stdout.strip()
        return CheckResult(name="git", passed=True, message=f"Found: {version}")
    except subprocess.TimeoutExpired:
        return CheckResult(name="git", passed=False, message="git --version timed out")
    except OSError as exc:
        return CheckResult(
            name="git", passed=False, message=f"Error running git: {exc}"
        )


def check_python_version() -> CheckResult:
    """Check whether the running Python interpreter is >= 3.11.

    Returns a :class:`CheckResult` indicating success or failure,
    including the detected version string.
    """
    vi = sys.version_info
    version_str = f"{vi.major}.{vi.minor}.{vi.micro}"
    if vi >= (3, 11):
        return CheckResult(
            name="python",
            passed=True,
            message=f"Python {version_str} (requirement met)",
        )
    return CheckResult(
        name="python",
        passed=False,
        message=f"Python {version_str} (requires >= 3.11)",
    )


def check_host_cli(host: str) -> CheckResult:
    """Check whether the CLI binary for *host* is available on PATH.

    Args:
        host: One of the supported host identifiers (e.g. ``"claude-code"``).

    Returns a :class:`CheckResult`.  If the host is unknown the check
    fails immediately with a descriptive message.
    """
    binaries = HOST_BINARIES.get(host)
    if binaries is None:
        return CheckResult(
            name=f"{host} CLI",
            passed=False,
            message=f"Unknown host '{host}'. Supported: {SUPPORTED_HOSTS}",
        )

    for binary in binaries:
        binary_path = shutil.which(binary)
        if binary_path:
            return CheckResult(
                name=f"{host} CLI",
                passed=True,
                message=f"Found '{binary}' at {binary_path}",
            )

    return CheckResult(
        name=f"{host} CLI",
        passed=False,
        message=f"None of {binaries} found on PATH",
    )


def run_doctor(host: str) -> list[CheckResult]:
    """Run all environment checks for *host* and return the results.

    Args:
        host: The coding host identifier to validate (e.g. ``"claude-code"``).

    Returns a list of :class:`CheckResult` objects, one per check.
    """
    return [
        check_git(),
        check_python_version(),
        check_host_cli(host),
    ]


def print_results(results: list[CheckResult]) -> bool:
    """Render check results to the terminal via rich and return overall pass/fail.

    Args:
        results: The list of :class:`CheckResult` objects to display.

    Returns ``True`` if every check passed, ``False`` otherwise.
    """
    all_passed = True
    for result in results:
        icon = "[green]PASS[/green]" if result.passed else "[red]FAIL[/red]"
        bracket = "[green][[/green]" if result.passed else "[red][[/red]"
        close = "[green]][/green]" if result.passed else "[red]][/red]"
        console.print(f"  {bracket}{icon}{close}  {result.name}: {result.message}")
        if not result.passed:
            all_passed = False
    return all_passed
