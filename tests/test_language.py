"""Tests for primary language detection."""

from __future__ import annotations

from pathlib import Path

from gradex.ai.language import detect_primary_language


def test_detect_node_from_package_json(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text('{"name": "app", "scripts": {"test": "vitest"}}')
    assert detect_primary_language(tmp_path) == "node"


def test_detect_python_from_pyproject(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'x'\n")
    assert detect_primary_language(tmp_path) == "python"


def test_detect_python_by_extension_majority(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x")
    (tmp_path / "b.py").write_text("y")
    (tmp_path / "c.ts").write_text("z")
    assert detect_primary_language(tmp_path) == "python"


def test_detect_node_by_extension_majority(tmp_path: Path) -> None:
    (tmp_path / "a.ts").write_text("x")
    (tmp_path / "b.js").write_text("y")
    (tmp_path / "c.tsx").write_text("z")
    assert detect_primary_language(tmp_path) == "node"
