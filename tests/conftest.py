"""Shared pytest fixtures for gradex tests."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def anyio_backend() -> str:
    """Use asyncio as the anyio backend for all async tests."""
    return "asyncio"


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """Create a minimal, committed git repository in *tmp_path* and return it."""
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    (tmp_path / "hello.py").write_text("print('hello')\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    return tmp_path
