"""The proactive digest pipeline (D5) — wires the four stages into one run.

    planner  ->  analysts (parallel)  ->  deterministic critic gate  ->  narrator

The critic is the load-bearing stage: if it refuses the cohort (right-censored target, or
no material finding survives its guards) the narrator never runs, so no LLM prose can smuggle
past the honesty contract. The narrator sees ONLY the critic struct, and its output is gated
by the numeric-faithfulness check before it may be cached.

Both the governed tools and the LLM are injected, so the whole pipeline is testable offline.
In production `tools` is `agents.tools.TOOL_FUNCTIONS` and `generate` is
`agents.narrator.genai_generator()` (Gemini free tier, D19).
"""
from __future__ import annotations

from typing import Any, Callable

from agents.analysts import run_analysts, to_critic_inputs
from agents.critic import critique
from agents.narrator import narrate
from agents.planner import plan_digest, select_cohorts


def run_digest(
    tools: dict[str, Callable[..., Any]],
    generate: Callable[[str], str],
    window: str = "msa_6",
    cohort: str | None = None,
    prior_cohort: str | None = None,
) -> dict:
    """Run one digest for `cohort` (auto-selected as the latest fully-observed cohort if omitted)."""
    blended = tools["query_metric"](metric_id="adoption_rate", window=window)["results"]

    if cohort is None:
        cohort, prior_cohort = select_cohorts(blended)

    plan = plan_digest(window=window, cohort=cohort, prior_cohort=prior_cohort)
    analyst_out = run_analysts(plan, tools=tools)
    series, target_cells, prior_cells = to_critic_inputs(analyst_out)

    struct = critique(
        window=window,
        cohort=cohort,
        prior_cohort=prior_cohort,
        blended_series=series,
        target_cells=target_cells,
        prior_cells=prior_cells,
        fully_observed_map={r["cohort"]: True for r in series},
    )

    if not struct["critic_passed"]:
        return {"critic_passed": False, "struct": struct, "digest": None}

    digest = narrate(struct, generate=generate)
    return {"critic_passed": True, "struct": struct, "digest": digest}
