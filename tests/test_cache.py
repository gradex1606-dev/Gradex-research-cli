"""Tests for benchmark cache behavior."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from gradex.runner.cache import BenchmarkCache, _cache_key, get_git_tree_hash


def test_cache_miss_returns_none(tmp_path: Path) -> None:
    cache = BenchmarkCache(db_path=tmp_path / "cache.db")
    result = cache.get("python bench.py", "abc123")
    assert result is None


def test_cache_put_and_hit(tmp_path: Path) -> None:
    cache = BenchmarkCache(db_path=tmp_path / "cache.db")
    cache.put("python bench.py", "abc123", 41.2)
    result = cache.get("python bench.py", "abc123")
    assert result == 41.2


def test_cache_different_tree_hash(tmp_path: Path) -> None:
    cache = BenchmarkCache(db_path=tmp_path / "cache.db")
    cache.put("python bench.py", "abc123", 41.2)
    result = cache.get("python bench.py", "def456")
    assert result is None


def test_cache_ttl_expiry(tmp_path: Path) -> None:
    cache = BenchmarkCache(db_path=tmp_path / "cache.db")
    cache.put("python bench.py", "abc123", 41.2)
    old_time = (datetime.utcnow() - timedelta(hours=25)).isoformat()
    cache._conn.execute(
        "UPDATE benchmark_cache SET created_at = ? WHERE key = ?",
        (old_time, _cache_key("python bench.py", "abc123")),
    )
    cache._conn.commit()
    result = cache.get("python bench.py", "abc123")
    assert result is None


def test_cache_empty_tree_hash_never_caches(tmp_path: Path) -> None:
    cache = BenchmarkCache(db_path=tmp_path / "cache.db")
    cache.put("python bench.py", "", 41.2)
    result = cache.get("python bench.py", "")
    assert result is None


def test_cache_clear_expired(tmp_path: Path) -> None:
    cache = BenchmarkCache(db_path=tmp_path / "cache.db")
    cache.put("python bench.py", "abc", 41.2)
    cache.put("python bench.py", "def", 38.0)
    old_time = (datetime.utcnow() - timedelta(hours=25)).isoformat()
    cache._conn.execute(
        "UPDATE benchmark_cache SET created_at = ? WHERE key = ?",
        (old_time, _cache_key("python bench.py", "abc")),
    )
    cache._conn.commit()
    deleted = cache.clear_expired()
    assert deleted == 1


def test_get_git_tree_hash_in_repo(git_repo: Path) -> None:
    result = get_git_tree_hash(git_repo)
    assert len(result) == 40


def test_get_git_tree_hash_not_repo(tmp_path: Path) -> None:
    result = get_git_tree_hash(tmp_path / "not_a_repo")
    assert result == ""


def test_cache_clear_all(tmp_path: Path) -> None:
    cache = BenchmarkCache(db_path=tmp_path / "cache.db")
    cache.put("python bench.py", "abc123", 41.2)
    cache.put("python bench.py", "def456", 40.1)
    cache.clear_all()
    assert cache.get("python bench.py", "abc123") is None
    assert cache.get("python bench.py", "def456") is None
