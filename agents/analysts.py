"""The analyst stage — deterministic, no LLM. Step 2 of the digest pipeline (D5).

Executes the planner's tasks against the governed tools and reshapes the results into the
exact inputs the critic consumes. The tasks are data-independent, so they run in parallel
(I/O-bound BigQuery reads) via a thread pool — the honest reason the pipeline is drawn as
"parallel analysts", not agent chatter. Tools return error-as-data (they never raise), so a
contract violation surfaces here as a structured ValueError rather than a leaked stack trace.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable


def run_analysts(plan: dict, tools: dict[str, Callable[..., Any]]) -> dict[str, Any]:
    """Run every planned task in parallel, keyed by task name."""
    def _run(task: dict) -> tuple[str, Any]:
        fn = tools[task["tool"]]
        return task["name"], fn(**task["args"])

    with ThreadPoolExecutor(max_workers=len(plan["tasks"]) or 1) as pool:
        return dict(pool.map(_run, plan["tasks"]))


def _require_results(result: Any, name: str) -> list[dict]:
    if isinstance(result, dict) and "error" in result:
        err = result["error"]
        raise ValueError(f"analyst task '{name}' failed: {err.get('code')} — {err.get('message')}")
    return result["results"]


def _cells(result: Any, name: str) -> list[dict]:
    return [
        {"segment": r["segment"], "value": r["value"], "n": r["n"]}
        for r in _require_results(result, name)
    ]


def to_critic_inputs(results: dict[str, Any]) -> tuple[list[dict], list[dict], list[dict]]:
    """Reshape analyst outputs into (blended_series, target_cells, prior_cells) for the critic."""
    series = _require_results(results["blended_trend"], "blended_trend")
    target_cells = _cells(results["segment_target"], "segment_target")
    prior_cells = _cells(results["segment_prior"], "segment_prior")
    return series, target_cells, prior_cells
