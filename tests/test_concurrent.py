"""Concurrency tests for TraceWriter and ExperimentRepository."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

import gradex.state as state_module
from gradex.repository import ExperimentRepository, RunRepository
from gradex.traces import TraceReader, TraceWriter


def test_concurrent_writes(tmp_path: Path) -> None:
    """10 threads each writing 10 entries to the same file produce 100 valid lines."""
    path = tmp_path / "shared.jsonl"
    writers = [TraceWriter(path) for _ in range(10)]

    errors: list[Exception] = []

    def write_ten(writer: TraceWriter) -> None:
        for i in range(10):
            try:
                writer.write("info", f"msg {i}")
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

    threads = [threading.Thread(target=write_ten, args=(w,)) for w in writers]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Write errors: {errors}"

    reader = TraceReader(path)
    entries = reader.read_all()
    assert len(entries) == 100, f"Expected 100, got {len(entries)}"
    # Every entry must be parseable (read_all already filters, so check raw count too)
    raw_lines = [
        ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()
    ]
    assert len(raw_lines) == 100


def test_concurrent_db_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """5 threads each creating 2 experiments yields 10 rows with no integrity errors."""
    evo_dir = tmp_path / ".gradex"
    monkeypatch.setattr(state_module, "GRADEX_DIR", evo_dir)
    monkeypatch.setattr(state_module, "DB_PATH", evo_dir / "state.db")

    run_repo = RunRepository()
    run = run_repo.create("bench", "higher", [], 0.0)

    exp_repo = ExperimentRepository()
    errors: list[Exception] = []

    def create_two() -> None:
        for _ in range(2):
            try:
                exp_repo.create(run_id=run.id, parent_id=None, branch="concurrent")
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

    threads = [threading.Thread(target=create_two) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"DB errors: {errors}"

    all_exps = exp_repo.list_by_run(run.id)
    assert len(all_exps) == 10
