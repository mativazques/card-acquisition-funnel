"""Execution layer over the governed metric registry — the four governed tools.

Plain Python (no LLM). `list_metrics` / `query_metric` / `compare_cohorts` /
`explain_metric` are what BI calls today and what every agent path (the reactive copilot,
the proactive ADK digest, the MCP wrapper) will wrap one-to-one in Phase 3 — text-to-metric,
never raw text-to-SQL. Every call validates against the registry and the window contract
and raises a structured `SemanticError` on violation, never leaking SQL or a stack trace.

Cohorts are acquisition months formatted `YYYY-MM` (e.g. '2015-06').
"""
from __future__ import annotations

import os
from functools import lru_cache

from google.cloud import bigquery

from .errors import SemanticError
from .metrics import METRICS, Metric
from .windows import Window, parse_window

_DBT_DATASET = os.environ.get("BQ_DBT_DATASET", "analytics")
_MARTS_DATASET = f"{_DBT_DATASET}_marts"
_PROJECT = os.environ.get("GCP_PROJECT", "card-acquisition-funnel-2026")


def _marts_table(name: str) -> str:
    return f"`{_PROJECT}.{_MARTS_DATASET}.{name}`"


@lru_cache(maxsize=1)
def _client() -> bigquery.Client:
    return bigquery.Client(project=_PROJECT)


def _resolve_metric(metric_id: str) -> Metric:
    metric = METRICS.get(metric_id)
    if metric is None:
        raise SemanticError(
            "metric_unknown",
            f"unknown metric '{metric_id}'; known: {sorted(METRICS)}",
        )
    return metric


def _resolve_window(metric: Metric, window: str | Window) -> Window:
    try:
        w = parse_window(window)
    except ValueError as exc:
        raise SemanticError("window_unknown", str(exc)) from exc
    if not metric.supports(w):
        raise SemanticError(
            "window_unsupported",
            f"metric '{metric.id}' does not support window '{w.value}'; "
            f"valid: {[x.value for x in metric.valid_windows]}",
        )
    return w


def list_metrics() -> list[dict]:
    """Catalog of governed metrics and the windows each one supports."""
    return [
        {
            "id": m.id,
            "label": m.label,
            "description": m.description,
            "unit": m.unit,
            "valid_windows": [w.value for w in m.valid_windows],
            "compositional": m.compositional,
        }
        for m in METRICS.values()
    ]


def explain_metric(metric_id: str) -> dict:
    """Full definition of one governed metric: windows and honesty caveats.

    A pure registry lookup ($0, no BigQuery) so an agent can narrate a metric's caveats
    verbatim instead of inventing them.
    """
    m = _resolve_metric(metric_id)
    return {
        "id": m.id,
        "label": m.label,
        "description": m.description,
        "unit": m.unit,
        "valid_windows": [w.value for w in m.valid_windows],
        "compositional": m.compositional,
        "caveats": list(m.caveats),
    }


def query_metric(
    metric_id: str,
    window: str | Window = Window.LIFETIME,
    cohort: str | None = None,
    dimension: str | None = None,
) -> dict:
    """Resolve a governed metric to per-cohort values (or one cohort's value).

    Scalar metrics return `results = [{"cohort", "value"}]`. Compositional metrics
    (segment_mix) return `results = [{"cohort", "breakdown": [{"dimension", "share"}]}]`.
    With `dimension="segmento"` (D17, supported metrics only) scalar metrics instead
    return `results = [{"cohort", "segment", "value", "n"}]` per fully-observed cell — the
    grain the by-segment analyst and the min-n guard consume.
    Raises SemanticError (structured) on an unknown metric, invalid window, or a dimension
    that is unknown or unsupported for the metric.
    """
    metric = _resolve_metric(metric_id)
    w = _resolve_window(metric, window)

    if dimension is not None:
        results = _query_by_dimension(metric, w, dimension)
    elif metric.compositional:
        results = _shape_compositional(list(_client().query(metric.build_sql(w, _marts_table)).result()))
    else:
        results = _shape_scalar(list(_client().query(metric.build_sql(w, _marts_table)).result()))

    if cohort is not None:
        picked = [r for r in results if r["cohort"] == cohort]
        if not picked:
            raise SemanticError(
                "cohort_unknown",
                f"no value for cohort '{cohort}' at window '{w.value}' "
                f"(it may be right-censored at this window)",
            )
        results = picked

    return {
        "metric": metric.id,
        "unit": metric.unit,
        "window": w.value,
        "dimension": dimension,
        "results": results,
    }


def _query_by_dimension(metric: Metric, w: Window, dimension: str) -> list[dict]:
    if dimension != "segmento":
        raise SemanticError(
            "dimension_unknown",
            f"unknown dimension '{dimension}'; supported: ['segmento']",
        )
    if metric.build_segment_sql is None:
        raise SemanticError(
            "dimension_unsupported",
            f"metric '{metric.id}' does not support a per-segment breakdown",
        )
    rows = list(_client().query(metric.build_segment_sql(w, _marts_table)).result())
    return _shape_segment(rows)


def _shape_segment(rows) -> list[dict]:
    return [
        {"cohort": r["cohort"], "segment": r["segment"], "value": r["value"], "n": r["n"]}
        for r in rows
        if r["value"] is not None
    ]


def _shape_scalar(rows) -> list[dict]:
    values = {r["cohort"]: r["value"] for r in rows}
    return [
        {"cohort": c, "value": values[c]}
        for c in sorted(values)
        if values[c] is not None
    ]


def _shape_compositional(rows) -> list[dict]:
    by_cohort: dict[str, list[dict]] = {}
    for r in rows:
        by_cohort.setdefault(r["cohort"], []).append(
            {"dimension": r["dimension"], "share": r["share"]}
        )
    return [
        {"cohort": c, "breakdown": by_cohort[c]} for c in sorted(by_cohort)
    ]


def compare_cohorts(
    cohort_a: str,
    cohort_b: str,
    metric_id: str,
    window: str | Window = Window.LIFETIME,
) -> dict:
    """Compare one scalar governed metric between two cohorts at the same window."""
    metric = _resolve_metric(metric_id)
    if metric.compositional:
        raise SemanticError(
            "metric_not_comparable",
            f"metric '{metric.id}' is compositional; use query_metric to read its "
            "per-cohort breakdown instead of compare_cohorts",
        )
    a = query_metric(metric_id, window, cohort_a)["results"][0]["value"]
    b = query_metric(metric_id, window, cohort_b)["results"][0]["value"]
    return {
        "metric": metric_id,
        "window": parse_window(window).value,
        "cohort_a": {"cohort": cohort_a, "value": a},
        "cohort_b": {"cohort": cohort_b, "value": b},
        "difference": None if a is None or b is None else a - b,
    }
