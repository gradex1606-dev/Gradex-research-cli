"""Thread-safe JSONL trace writer and reader for evo experiment traces."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

import gradex.state as _state  # reference via module so monkeypatching GRADEX_DIR works
from gradex.security.scrubber import scrub, scrub_dict

# ---------------------------------------------------------------------------
# Module-level per-path lock registry — guarantees serialised writes to any
# given file even when multiple TraceWriter instances target the same path.
# ---------------------------------------------------------------------------

_file_locks: dict[str, threading.Lock] = {}
_registry_lock = threading.Lock()


def _get_file_lock(path: Path) -> threading.Lock:
    key = str(path.resolve())
    with _registry_lock:
        if key not in _file_locks:
            _file_locks[key] = threading.Lock()
        return _file_locks[key]


def trace_path_for(experiment_id: str) -> Path:
    """Return the canonical JSONL trace path for *experiment_id*.

    Resolves against the module-level ``evo.state.GRADEX_DIR`` so that test
    monkeypatching of that attribute is honoured here as well.
    """
    return _state.GRADEX_DIR / "traces" / f"{experiment_id}.jsonl"


class TraceWriter:
    """Append-only, thread-safe writer for a JSONL trace file."""

    def __init__(self, path: Path) -> None:
        """Initialise the writer for *path*, creating parent directories."""
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def write(
        self,
        level: str,
        msg: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        """Append one trace entry to the file.

        Args:
            level: Severity string — ``"info"``, ``"warn"``, or ``"error"``.
            msg:   Human-readable message.
            data:  Optional key/value payload.  Defaults to an empty dict.
        """
        clean_msg = scrub(msg)
        clean_data = scrub_dict(data if data is not None else {})
        entry: dict[str, Any] = {
            "ts": time.time(),
            "level": level,
            "msg": clean_msg,
            "data": clean_data,
        }
        line = json.dumps(entry) + "\n"
        lock = _get_file_lock(self._path)
        with lock:
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(line)


class TraceReader:
    """Sequential reader for a JSONL trace file."""

    def __init__(self, path: Path) -> None:
        """Initialise the reader for *path*."""
        self._path = path

    def read_all(self) -> list[dict[str, Any]]:
        """Parse and return all valid trace entries from the file.

        Malformed (non-JSON) lines are silently skipped.
        Returns an empty list if the file does not exist.
        """
        if not self._path.exists():
            return []
        entries: list[dict[str, Any]] = []
        with self._path.open("r", encoding="utf-8") as fh:
            for raw in fh:
                stripped = raw.strip()
                if not stripped:
                    continue
                try:
                    entries.append(json.loads(stripped))
                except json.JSONDecodeError:
                    continue
        return entries

    def tail(self, n: int) -> list[dict[str, Any]]:
        """Return the last *n* trace entries.

        Args:
            n: Maximum number of entries to return.
        """
        return self.read_all()[-n:]
