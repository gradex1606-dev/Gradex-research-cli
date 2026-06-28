"""Primary language detection for discover."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

PrimaryLanguage = Literal["python", "node"]


def detect_primary_language(repo_root: Path) -> PrimaryLanguage:
    """Detect the repo's primary language for benchmark and gate design."""
    if (repo_root / "package.json").is_file():
        return "node"

    for marker in ("pyproject.toml", "setup.py", "requirements.txt"):
        if (repo_root / marker).is_file():
            return "python"

    py_count = 0
    js_count = 0
    for path in repo_root.rglob("*"):
        if not path.is_file():
            continue
        if any(part.startswith(".") for part in path.parts):
            continue
        suffix = path.suffix.lower()
        if suffix == ".py":
            py_count += 1
        elif suffix in {".js", ".ts", ".tsx", ".mjs", ".cjs"}:
            js_count += 1

    if js_count > py_count and js_count > 0:
        return "node"
    return "python"


def package_json_has_tests(repo_root: Path) -> bool:
    """Return True when package.json defines a test script."""
    pkg_path = repo_root / "package.json"
    if not pkg_path.is_file():
        return False
    try:
        data = json.loads(pkg_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    scripts = data.get("scripts", {})
    return isinstance(scripts, dict) and "test" in scripts
