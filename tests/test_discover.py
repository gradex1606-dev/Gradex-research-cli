"""Tests for DiscoverSkill — all LLM calls are mocked."""

from __future__ import annotations

from pathlib import Path

import pytest

from gradex.ai.client import LLMClient, LLMResponse
from gradex.ai.discover import DiscoverSkill
from gradex.backends.base import Backend, CommandResult
from gradex.config import LLMConfig

# ---------------------------------------------------------------------------
# Shared mock infrastructure
# ---------------------------------------------------------------------------


class _NullBackend(Backend):
    """Backend that does nothing — used for tests that never run commands."""

    async def create_workspace(self, experiment_id: str) -> Path:  # noqa: D102
        return Path("/fake")

    async def run_command(
        self,
        workspace_path: Path,
        cmd: list[str],
        timeout: int = 120,
        env: dict[str, str] | None = None,
    ) -> CommandResult:  # noqa: D102
        raise AssertionError("run_command should not be called in this test")

    async def cleanup_workspace(self, workspace_path: Path) -> None:  # noqa: D102
        pass

    def list_workspaces(self) -> list[Path]:  # noqa: D102
        return []


def _make_skill(responses: list[str] | None = None) -> DiscoverSkill:
    """Return a DiscoverSkill wired to a _NullBackend with preset LLM responses."""
    config = LLMConfig(provider="anthropic")
    client = LLMClient(config)
    if responses is not None:
        _resp_iter = iter(responses)

        async def _mock_complete(
            system: str, user: str, max_tokens: int | None = None
        ) -> LLMResponse:
            text = next(_resp_iter, "")
            return LLMResponse(
                text=text,
                input_tokens=5,
                output_tokens=5,
                provider="mock",
                model="mock",
            )

        client.complete = _mock_complete  # type: ignore[method-assign]
    return DiscoverSkill(client=client, backend=_NullBackend())


# ---------------------------------------------------------------------------
# scan_repo tests
# ---------------------------------------------------------------------------


def test_scan_repo_output(tmp_path: Path) -> None:
    """scan_repo returns relative paths and extension counts."""
    (tmp_path / "a.py").write_text("x = 1")
    (tmp_path / "b.py").write_text("y = 2")
    (tmp_path / "c.py").write_text("z = 3")
    sub = tmp_path / "subdir"
    sub.mkdir()
    (sub / "d.py").write_text("w = 4")

    skill = _make_skill()
    result = skill.scan_repo(tmp_path)

    assert ".py" in result
    assert str(tmp_path) not in result  # paths must be relative (item names only)


def test_scan_repo_skips_hidden(tmp_path: Path) -> None:
    """scan_repo omits .git and __pycache__ directories."""
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("git config")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "x.pyc").write_text("")
    (tmp_path / "main.py").write_text("pass")

    skill = _make_skill()
    result = skill.scan_repo(tmp_path)

    assert ".git" not in result
    assert "__pycache__" not in result
    assert "main.py" in result


# ---------------------------------------------------------------------------
# _parse_xml_tag tests
# ---------------------------------------------------------------------------


def test_parse_xml_tag_success() -> None:
    """Content between matching tags is extracted and stripped."""
    skill = _make_skill()
    assert (
        skill._parse_xml_tag("blah <foo>hello world</foo> blah", "foo") == "hello world"
    )


def test_parse_xml_tag_missing_raises() -> None:
    """A missing tag raises ValueError."""
    skill = _make_skill()
    with pytest.raises(ValueError):
        skill._parse_xml_tag("no tags here", "foo")


# ---------------------------------------------------------------------------
# _infer_direction tests
# ---------------------------------------------------------------------------


def test_infer_direction_lower() -> None:
    """Latency / cost / ms keywords infer 'lower'."""
    skill = _make_skill()
    for hint in ["latency in ms, lower is better", "minimize cost", "latency"]:
        assert skill._infer_direction(hint) == "lower", hint


def test_infer_direction_higher() -> None:
    """Accuracy / score / throughput keywords infer 'higher'."""
    skill = _make_skill()
    for hint in ["accuracy %, higher is better", "maximize throughput", "score"]:
        assert skill._infer_direction(hint) == "higher", hint


# ---------------------------------------------------------------------------
# detect_test_files tests
# ---------------------------------------------------------------------------


def test_detect_test_files(tmp_path: Path) -> None:
    """Both test_*.py and *_test.py are detected under any subdirectory."""
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_parser.py").write_text("")
    (tmp_path / "test_main.py").write_text("")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "parser_test.py").write_text("")

    skill = _make_skill()
    files = skill.detect_test_files(tmp_path)

    assert len(files) == 3
    assert all(f.endswith(".py") for f in files)


def test_normalize_gate_cmds_falls_back_to_detected_tests(tmp_path: Path) -> None:
    """Invented pytest paths are replaced with detected test files."""
    (tmp_path / "test_parser.py").write_text("")

    skill = _make_skill()
    cmds = skill._normalize_gate_cmds(
        ["pytest tests/missing.py"],
        tmp_path,
        ["test_parser.py"],
    )

    assert cmds == ["pytest test_parser.py"]


def test_normalize_gate_cmds_keeps_valid_paths(tmp_path: Path) -> None:
    """Existing pytest targets are kept as-is."""
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_parser.py").write_text("")

    skill = _make_skill()
    cmds = skill._normalize_gate_cmds(
        ["pytest tests/test_parser.py"],
        tmp_path,
        ["tests/test_parser.py"],
    )

    assert cmds == ["pytest tests/test_parser.py"]


# ---------------------------------------------------------------------------
# Full discover flow integration test
# ---------------------------------------------------------------------------


@pytest.fixture
def patch_evo_dir(git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect GRADEX_DIR and DB_PATH into the test git repo so DB and worktrees are isolated."""
    evo_dir = git_repo / ".gradex"
    monkeypatch.setattr("gradex.state.GRADEX_DIR", evo_dir)
    monkeypatch.setattr("gradex.state.DB_PATH", evo_dir / "state.db")
    monkeypatch.setattr("gradex.backends.worktree.GRADEX_DIR", evo_dir)


@pytest.mark.anyio
async def test_full_discover_flow(git_repo: Path, patch_evo_dir: None) -> None:
    """Full discover flow: three mocked LLM calls → baseline run → Run record."""
    from gradex.backends.worktree import WorktreeBackend

    llm_responses = [
        # Call 1 — repo analysis
        (
            "<optimization_target>Make the parser faster</optimization_target>"
            "<metric>latency in ms, lower is better</metric>"
            "<rationale>Hot path.</rationale>"
        ),
        # Call 2 — benchmark design
        "<benchmark_script>print(41.2)</benchmark_script><notes/>",
        # Call 3 — gate design
        '<gate_cmds>["python -c \\"exit(0)\\""]</gate_cmds><rationale>Covers it.</rationale>',
    ]

    config = LLMConfig(provider="anthropic")
    client = LLMClient(config)
    resp_iter = iter(llm_responses)

    async def _mock_complete(
        system: str, user: str, max_tokens: int | None = None
    ) -> LLMResponse:
        text = next(resp_iter, "")
        return LLMResponse(
            text=text, input_tokens=5, output_tokens=5, provider="mock", model="mock"
        )

    client.complete = _mock_complete  # type: ignore[method-assign]

    backend = WorktreeBackend(repo_root=git_repo)
    skill = DiscoverSkill(client=client, backend=backend)

    result = await skill.run(git_repo)

    assert result.optimization_target != ""
    assert result.baseline_score == pytest.approx(41.2)
    assert result.run_id != ""
    assert (git_repo / ".gradex" / "benchmark.py").exists()
