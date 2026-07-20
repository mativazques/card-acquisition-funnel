"""The tools edge — the single boundary every agent path shares.

Wraps the four governed tools from `semantic/` one-to-one, adding exactly two things the raw
semantic package deliberately does not carry (D15 keeps it framework-neutral):

1. **Error-as-data.** A `SemanticError` (unknown metric, invalid window, unsupported
   dimension) is returned as a structured `{"error": {...}}` dict instead of raised — an LLM
   function-calling runtime cannot catch a Python exception, so a contract violation must come
   back as a normal tool result the model can read and correct.
2. **Tool declarations.** `TOOL_DECLARATIONS` are Gemini-style function schemas so the
   reactive copilot, the proactive ADK analysts, and the MCP wrapper can all bind the same
   four callables without re-describing them.

Text-to-metric end to end: these are the only tools any agent may call.
"""
from __future__ import annotations

from typing import Any, Callable

from semantic import compare_cohorts, explain_metric, list_metrics, query_metric
from semantic.errors import SemanticError


def _as_data(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    try:
        return fn(*args, **kwargs)
    except SemanticError as exc:
        return exc.as_dict()


def tool_list_metrics() -> Any:
    return _as_data(list_metrics)


def tool_query_metric(
    metric_id: str,
    window: str = "lifetime",
    cohort: str | None = None,
    dimension: str | None = None,
) -> Any:
    return _as_data(query_metric, metric_id, window, cohort, dimension)


def tool_compare_cohorts(
    cohort_a: str,
    cohort_b: str,
    metric_id: str,
    window: str = "lifetime",
) -> Any:
    return _as_data(compare_cohorts, cohort_a, cohort_b, metric_id, window)


def tool_explain_metric(metric_id: str) -> Any:
    return _as_data(explain_metric, metric_id)


TOOL_FUNCTIONS: dict[str, Callable[..., Any]] = {
    "list_metrics": tool_list_metrics,
    "query_metric": tool_query_metric,
    "compare_cohorts": tool_compare_cohorts,
    "explain_metric": tool_explain_metric,
}

_METRIC_ID = {"type": "string", "description": "A governed metric id (see list_metrics)."}
_WINDOW = {
    "type": "string",
    "description": "A window from the governed enum (e.g. msa_3, msa_6, ret_1m); "
    "each metric declares its valid windows.",
}

TOOL_DECLARATIONS: list[dict[str, Any]] = [
    {
        "name": "list_metrics",
        "description": "List every governed metric and the windows each supports.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "query_metric",
        "description": (
            "Resolve a governed metric to per-cohort values. With dimension='segmento' it "
            "returns per-segment cells carrying both value and n (for the by-segment slice)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "metric_id": _METRIC_ID,
                "window": _WINDOW,
                "cohort": {
                    "type": "string",
                    "description": "Acquisition cohort as YYYY-MM (e.g. 2015-06); omit for all.",
                },
                "dimension": {
                    "type": "string",
                    "description": "Optional breakdown; only 'segmento' is supported.",
                    "enum": ["segmento"],
                },
            },
            "required": ["metric_id"],
        },
    },
    {
        "name": "compare_cohorts",
        "description": "Compare one scalar governed metric between two cohorts at one window.",
        "parameters": {
            "type": "object",
            "properties": {
                "cohort_a": {"type": "string", "description": "First cohort as YYYY-MM."},
                "cohort_b": {"type": "string", "description": "Second cohort as YYYY-MM."},
                "metric_id": _METRIC_ID,
                "window": _WINDOW,
            },
            "required": ["cohort_a", "cohort_b", "metric_id"],
        },
    },
    {
        "name": "explain_metric",
        "description": "Return one metric's definition, valid windows, and honesty caveats.",
        "parameters": {
            "type": "object",
            "properties": {"metric_id": _METRIC_ID},
            "required": ["metric_id"],
        },
    },
]
