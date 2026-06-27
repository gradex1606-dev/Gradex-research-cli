"""Tests for gradex.export — RunExporter."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

import gradex.state as state_module

# ---------------------------------------------------------------------------
# Fixture (same seeded run as test_analytics.py)
# ---------------------------------------------------------------------------


@pytest.fixture()
def seeded_run(tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch):  # type: ignore[type-arg]
    """Create a run with 7 experiments: 3 passed, 2 rejected, 2 failed."""
    gradex_dir = tmp_path / ".gradex"
    monkeypatch.setattr(state_module, "GRADEX_DIR", gradex_dir)
    monkeypatch.setattr(state_module, "DB_PATH", gradex_dir / "state.db")

    from gradex.repository import ExperimentRepository, RunRepository

    run_repo = RunRepository()
    exp_repo = ExperimentRepository()

    run = run_repo.create("python bench.py", "lower", ["pytest tests/"], 41.2)
    experiments = [
        ("passed", 38.1, True),
        ("rejected", 29.0, False),
        ("passed", 35.6, True),
        ("failed", None, None),
        ("passed", 31.4, True),
        ("rejected", 28.0, False),
        ("failed", None, None),
    ]
    for status, score, gate in experiments:
        exp = exp_repo.create(run.id, None, "gradex/exp")
        if score is not None and gate is not None:
            exp_repo.update_score(exp.id, score, gate, status)
        elif status == "failed":
            from sqlmodel import Session, select

            from gradex.state import Experiment, get_engine

            with Session(get_engine()) as session:
                result = session.exec(select(Experiment).where(Experiment.id == exp.id))
                db_exp = result.one()
                db_exp.status = "failed"
                session.add(db_exp)
                session.commit()

    return run


# ---------------------------------------------------------------------------
# JSON export
# ---------------------------------------------------------------------------


def test_export_json_structure(seeded_run, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    from gradex.export import RunExporter

    exporter = RunExporter()
    path = exporter.to_json(seeded_run.id, tmp_path / "run.json")
    assert path.exists()
    data = json.loads(path.read_text())
    assert "summary" in data
    assert "score_over_time" in data
    assert "experiments" in data
    assert data["summary"]["run_id_short"] == seeded_run.id[:8]


def test_export_json_datetimes_are_strings(seeded_run, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    from gradex.export import RunExporter

    exporter = RunExporter()
    path = exporter.to_json(seeded_run.id, tmp_path / "run.json")
    data = json.loads(path.read_text())
    # Datetimes must be ISO strings, not datetime objects
    created_at = data["summary"].get("created_at", "ok")
    assert isinstance(created_at, str)


def test_export_json_experiment_count(seeded_run, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    from gradex.export import RunExporter

    exporter = RunExporter()
    path = exporter.to_json(seeded_run.id, tmp_path / "run.json")
    data = json.loads(path.read_text())
    assert len(data["experiments"]) == 7


def test_export_json_score_over_time_only_passed(seeded_run, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    from gradex.export import RunExporter

    exporter = RunExporter()
    path = exporter.to_json(seeded_run.id, tmp_path / "run.json")
    data = json.loads(path.read_text())
    assert len(data["score_over_time"]) == 3  # only passed


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------


def test_export_csv_columns(seeded_run, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    from gradex.export import RunExporter

    exporter = RunExporter()
    path = exporter.to_csv(seeded_run.id, tmp_path / "run.csv")
    assert path.exists()
    with open(path) as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    assert len(rows) == 7
    assert "id" in rows[0]
    assert "status" in rows[0]
    assert "score" in rows[0]


def test_export_csv_scores_formatted(seeded_run, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    from gradex.export import RunExporter

    exporter = RunExporter()
    path = exporter.to_csv(seeded_run.id, tmp_path / "run.csv")
    with open(path) as f:
        rows = list(csv.DictReader(f))
    # passed experiments should have numeric scores
    passed_rows = [r for r in rows if r["status"] == "passed"]
    assert len(passed_rows) == 3
    assert all(r["score"] != "" for r in passed_rows)


def test_export_html_creates_file(seeded_run, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    from gradex.export import RunExporter

    exporter = RunExporter()
    path = exporter.to_html(seeded_run.id, tmp_path / "report.html")
    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert "GradeX Run Report" in content
    assert seeded_run.id[:8] in content
    assert "<table>" in content
