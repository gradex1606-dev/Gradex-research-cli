"""SQLModel database models and SQLite engine factory for gradex."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from sqlalchemy import Engine, text
from sqlmodel import Field, SQLModel, create_engine

# Module-level paths so that tests can monkeypatch them before calling get_engine().
GRADEX_DIR = Path(".gradex")
DB_PATH = GRADEX_DIR / "state.db"


def get_engine() -> Engine:
    """Create a SQLite engine pointing at DB_PATH, with WAL mode and all tables.

    GRADEX_DIR is created on demand.  Because this function reads the module-level
    ``GRADEX_DIR`` and ``DB_PATH`` names at call time, tests can monkeypatch those
    attributes to redirect the DB to a temporary directory.
    """
    GRADEX_DIR.mkdir(parents=True, exist_ok=True)
    try:
        cwd = Path.cwd()
        git_dir = cwd / ".git"
        gitignore = cwd / ".gitignore"
        should_manage = gitignore.exists() or git_dir.exists()
        if should_manage:
            if gitignore.exists():
                existing = gitignore.read_text(encoding="utf-8")
            else:
                existing = ""
            lines = {line.strip() for line in existing.splitlines()}
            if ".gradex/" not in lines:
                with gitignore.open("a", encoding="utf-8") as fh:
                    if existing and not existing.endswith("\n"):
                        fh.write("\n")
                    fh.write(".gradex/\n")
    except Exception:  # noqa: BLE001
        pass
    engine = create_engine(
        f"sqlite:///{DB_PATH}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    with engine.connect() as conn:
        conn.execute(text("PRAGMA journal_mode=WAL"))
        conn.commit()
    SQLModel.metadata.create_all(engine)
    return engine


class Run(SQLModel, table=True):
    """Top-level benchmark run, owning a set of :class:`Experiment` records."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    benchmark_cmd: str
    metric_direction: str  # "higher" | "lower"
    gate_cmds: str = Field(default="[]")  # JSON-encoded list[str]
    baseline_score: float
    baseline_experiment_id: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def get_gate_cmds(self) -> list[str]:
        """Deserialize the JSON ``gate_cmds`` column into a Python list."""
        return cast(list[str], json.loads(self.gate_cmds))

    def set_gate_cmds(self, cmds: list[str]) -> None:
        """Serialize *cmds* and store them in the ``gate_cmds`` column."""
        self.gate_cmds = json.dumps(cmds)


class Experiment(SQLModel, table=True):
    """A single experiment attempt within a :class:`Run`."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    run_id: str = Field(index=True)
    parent_id: str | None = None
    branch: str
    score: float | None = None
    gate_passed: bool | None = None
    status: str = "pending"  # pending | running | passed | failed | rejected
    traces_path: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
