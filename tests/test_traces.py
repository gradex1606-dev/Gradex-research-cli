"""Tests for TraceWriter, TraceReader, and trace_path_for."""

from __future__ import annotations

from pathlib import Path

from gradex.traces import TraceReader, TraceWriter, trace_path_for


def test_write_and_read(tmp_path: Path) -> None:
    """Writing 5 entries and reading them back returns 5 entries in order."""
    path = tmp_path / "trace.jsonl"
    writer = TraceWriter(path)
    for i in range(5):
        writer.write("info", f"message {i}", {"index": i})

    reader = TraceReader(path)
    entries = reader.read_all()
    assert len(entries) == 5
    for i, entry in enumerate(entries):
        assert entry["msg"] == f"message {i}"
        assert entry["level"] == "info"
        assert entry["data"]["index"] == i


def test_tail(tmp_path: Path) -> None:
    """tail(3) on 10 entries returns only the last 3."""
    path = tmp_path / "trace.jsonl"
    writer = TraceWriter(path)
    for i in range(10):
        writer.write("info", f"msg {i}")

    reader = TraceReader(path)
    last = reader.tail(3)
    assert len(last) == 3
    assert last[0]["msg"] == "msg 7"
    assert last[1]["msg"] == "msg 8"
    assert last[2]["msg"] == "msg 9"


def test_skip_malformed(tmp_path: Path) -> None:
    """read_all skips non-JSON lines and returns the valid entries."""
    path = tmp_path / "trace.jsonl"
    writer = TraceWriter(path)
    writer.write("info", "before")
    # Inject a corrupted line directly
    with path.open("a", encoding="utf-8") as fh:
        fh.write("THIS IS NOT JSON\n")
    writer.write("info", "after")

    reader = TraceReader(path)
    entries = reader.read_all()
    assert len(entries) == 2
    assert entries[0]["msg"] == "before"
    assert entries[1]["msg"] == "after"


def test_trace_path() -> None:
    """trace_path_for returns the expected sub-path structure."""
    result = trace_path_for("abc-123")
    assert result.name == "abc-123.jsonl"
    assert result.parent.name == "traces"
