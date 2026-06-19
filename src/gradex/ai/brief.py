"""Brief generator: render the per-experiment optimisation prompt template."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import jinja2

from gradex.ai.client import LLMClient

_PROMPTS_DIR = Path(__file__).parent / "prompts"


@dataclass
class ExperimentSummary:
    """A compact summary of one past experiment for inclusion in a brief."""

    hypothesis: str
    result: str  # "improved" | "regressed" | "gate_failed" | "failed"
    reason: str  # e.g. "score went from 41.2 to 45.0 (regression)"


class BriefGenerator:
    """Renders ``optimize_brief.md`` into a Markdown prompt for a subagent.

    ``generate()`` is **synchronous** — briefs are pure Jinja2 template
    renders, not LLM calls.  The subagent that *receives* the brief is the
    LLM.
    """

    def __init__(self, client: LLMClient) -> None:
        # Client stored for future extensions; not used in synchronous rendering.
        self._client = client

    def generate(
        self,
        optimization_target: str,
        metric: str,
        metric_direction: str,
        baseline_score: float,
        best_score: float,
        benchmark_cmd: str,
        gate_cmd: str,
        past_experiments: list[ExperimentSummary],
        shared_notes: str = "",
        agent_index: int = 0,
    ) -> str:
        """Render the optimisation brief for one parallel agent.

        Args:
            optimization_target: One-sentence description of the target.
            metric:              Human-readable metric string.
            metric_direction:    ``"higher"`` or ``"lower"``.
            baseline_score:      Score at the start of the run.
            best_score:          Best score seen so far.
            benchmark_cmd:       Shell command to run the benchmark.
            gate_cmd:            Shell command to run the gate tests.
            past_experiments:    History of previous attempts.
            shared_notes:        Cross-agent knowledge to include.
            agent_index:         Controls experiment ordering for variety.
                                 Index 0 → oldest-first;
                                 Index > 0 → reversed (newest-first) for diversity.

        Returns the rendered Markdown string; never calls the LLM.
        """
        template = self._load_template()

        # Vary ordering so parallel agents explore different strategies.
        experiments = list(past_experiments)
        if agent_index > 0 and experiments:
            experiments = list(reversed(experiments))

        return template.render(
            optimization_target=optimization_target,
            metric=metric,
            direction=metric_direction,
            baseline_score=baseline_score,
            best_score=best_score,
            benchmark_cmd=benchmark_cmd,
            gate_cmd=gate_cmd,
            failed_experiments=experiments,
            shared_notes=shared_notes,
        )

    def _load_template(self) -> jinja2.Template:
        """Load ``optimize_brief.md`` as a Jinja2 :class:`~jinja2.Template`."""
        env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(_PROMPTS_DIR)),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
        )
        return env.get_template("optimize_brief.md")
