"""The planner — deterministic, no LLM. Step 1 of the proactive digest pipeline (D5).

Given the fully-observed blended adoption series, it picks the target cohort (the latest
narratable one) and its predecessor, then emits the fixed set of analyst tasks the digest
needs. Every task calls ONLY the governed `query_metric` tool (D7 text-to-metric): one
blended-trend read plus two per-segment reads (target and prior). The plan is a plain data
structure so the analyst stage can execute the independent tasks in parallel.
"""
from __future__ import annotations


def select_cohorts(blended_series: list[dict]) -> tuple[str, str]:
    """Target = last cohort in the ascending fully-observed series, prior = the one before.

    The series is already filtered to fully-observed cohorts upstream, so the last element
    is the latest cohort we may narrate. Needs at least two cohorts to form a delta.
    """
    if len(blended_series) < 2:
        raise ValueError("need at least two fully-observed cohorts to plan a digest")
    return blended_series[-1]["cohort"], blended_series[-2]["cohort"]


def plan_digest(window: str, cohort: str, prior_cohort: str) -> dict:
    """Emit the fixed analyst tasks for one target cohort at one window."""
    return {
        "window": window,
        "cohort": cohort,
        "prior_cohort": prior_cohort,
        "tasks": [
            {
                "name": "blended_trend",
                "tool": "query_metric",
                "args": {"metric_id": "adoption_rate", "window": window},
            },
            {
                "name": "segment_target",
                "tool": "query_metric",
                "args": {
                    "metric_id": "adoption_rate",
                    "window": window,
                    "cohort": cohort,
                    "dimension": "segmento",
                },
            },
            {
                "name": "segment_prior",
                "tool": "query_metric",
                "args": {
                    "metric_id": "adoption_rate",
                    "window": window,
                    "cohort": prior_cohort,
                    "dimension": "segmento",
                },
            },
        ],
    }
