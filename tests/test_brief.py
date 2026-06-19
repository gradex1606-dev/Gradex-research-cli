"""Tests for BriefGenerator — synchronous template rendering, no LLM calls."""

from __future__ import annotations

from gradex.ai.brief import BriefGenerator, ExperimentSummary
from gradex.ai.client import LLMClient, LLMResponse
from gradex.config import LLMConfig

# ---------------------------------------------------------------------------
# Mock LLMClient — tracks call count to verify generate() never calls it
# ---------------------------------------------------------------------------


class _CountingClient(LLMClient):
    """LLMClient subclass that records every complete() invocation."""

    def __init__(self) -> None:
        super().__init__(LLMConfig(provider="anthropic"))
        self.call_count = 0

    async def complete(
        self, system: str, user: str, max_tokens: int | None = None
    ) -> LLMResponse:
        self.call_count += 1
        return LLMResponse(
            text="", input_tokens=0, output_tokens=0, provider="mock", model="mock"
        )


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _gen(client: _CountingClient) -> BriefGenerator:
    return BriefGenerator(client=client)


_EXPERIMENTS = [
    ExperimentSummary("try memoization", "regressed", "score went from 41.2 to 45.0"),
    ExperimentSummary("inline the loop", "gate_failed", "2 tests failed"),
    ExperimentSummary("vectorise parse", "improved", "score dropped to 38.1"),
]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_brief_renders_without_llm() -> None:
    """generate() returns a Markdown string and never touches the LLM."""
    client = _CountingClient()
    brief = _gen(client).generate(
        optimization_target="make parser faster",
        metric="latency ms",
        metric_direction="lower",
        baseline_score=41.2,
        best_score=35.0,
        benchmark_cmd="python .gradex/benchmark.py",
        gate_cmd="pytest tests/",
        past_experiments=_EXPERIMENTS[:2],
        agent_index=0,
    )

    assert "make parser faster" in brief
    assert "41.2" in brief
    assert "memoization" in brief
    assert "inline the loop" in brief
    assert client.call_count == 0  # synchronous — no LLM call


def test_briefs_differ_by_agent_index() -> None:
    """agent_index=0 and agent_index=2 produce different experiment orderings."""
    client = _CountingClient()
    gen = _gen(client)

    common: dict[str, object] = {
        "optimization_target": "target",
        "metric": "latency",
        "metric_direction": "lower",
        "baseline_score": 50.0,
        "best_score": 40.0,
        "benchmark_cmd": "python bench.py",
        "gate_cmd": "pytest",
        "past_experiments": list(_EXPERIMENTS),
        "shared_notes": "",
    }

    brief0 = gen.generate(**common, agent_index=0)  # type: ignore[arg-type]
    brief2 = gen.generate(**common, agent_index=2)  # type: ignore[arg-type]

    # Both briefs must render but in a different order.
    assert brief0 != brief2


def test_brief_empty_past_experiments() -> None:
    """generate() renders cleanly when past_experiments is an empty list."""
    client = _CountingClient()
    brief = _gen(client).generate(
        optimization_target="speed up tokeniser",
        metric="ms per call",
        metric_direction="lower",
        baseline_score=10.0,
        best_score=10.0,
        benchmark_cmd="python bench.py",
        gate_cmd="pytest",
        past_experiments=[],
        agent_index=0,
    )

    # Template section header may still appear, but no list items should.
    assert "do NOT repeat" not in brief or brief.count("\n-") == 0
