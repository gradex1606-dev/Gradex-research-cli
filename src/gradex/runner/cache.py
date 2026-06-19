"""Synchronous benchmark score cache backed by SQLite."""

from __future__ import annotations

import hashlib
import sqlite3
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from gradex.state import GRADEX_DIR

CACHE_DB = GRADEX_DIR / "benchmark_cache.db"
CACHE_TTL_HOURS = 24


def _cache_key(benchmark_cmd: str, git_tree_hash: str) -> str:
    """SHA256 of benchmark command and git tree hash."""
    payload = f"{benchmark_cmd}||{git_tree_hash}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def get_git_tree_hash(repo_root: Path) -> str:
    """Return ``git rev-parse HEAD`` hash, or empty string on failure."""
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
        return proc.stdout.strip()
    except Exception:  # noqa: BLE001
        return ""


class BenchmarkCache:
    """SQLite-backed cache for benchmark scores."""

    def __init__(self, db_path: Path | None = None) -> None:
        path = db_path or CACHE_DB
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS benchmark_cache (
                key TEXT PRIMARY KEY,
                score REAL NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    def get(self, benchmark_cmd: str, git_tree_hash: str) -> float | None:
        """Get cached score if fresh; return ``None`` on miss/expired/invalid hash."""
        if not git_tree_hash:
            return None
        key = _cache_key(benchmark_cmd, git_tree_hash)
        row = self._conn.execute(
            "SELECT score, created_at FROM benchmark_cache WHERE key = ?",
            (key,),
        ).fetchone()
        if row is None:
            return None

        score = float(row[0])
        created_at = datetime.fromisoformat(str(row[1]))
        if datetime.utcnow() - created_at > timedelta(hours=CACHE_TTL_HOURS):
            self._conn.execute("DELETE FROM benchmark_cache WHERE key = ?", (key,))
            self._conn.commit()
            return None
        return score

    def put(self, benchmark_cmd: str, git_tree_hash: str, score: float) -> None:
        """Insert or replace cache entry."""
        if not git_tree_hash:
            return
        key = _cache_key(benchmark_cmd, git_tree_hash)
        self._conn.execute(
            """
            INSERT OR REPLACE INTO benchmark_cache (key, score, created_at)
            VALUES (?, ?, ?)
            """,
            (key, score, datetime.utcnow().isoformat()),
        )
        self._conn.commit()

    def clear_expired(self) -> int:
        """Delete expired entries and return deleted row count."""
        cutoff = (datetime.utcnow() - timedelta(hours=CACHE_TTL_HOURS)).isoformat()
        cur = self._conn.execute(
            "DELETE FROM benchmark_cache WHERE created_at < ?",
            (cutoff,),
        )
        self._conn.commit()
        return int(cur.rowcount if cur.rowcount is not None else 0)

    def clear_all(self) -> None:
        """Delete all cache entries."""
        self._conn.execute("DELETE FROM benchmark_cache")
        self._conn.commit()
