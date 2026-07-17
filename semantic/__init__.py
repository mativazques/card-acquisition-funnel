"""Governed semantic layer: metric definitions consumed by BI and every agent path.

Framework-neutral by design (D15): this package is a plain-Python source of truth that
Streamlit imports today, and that the reactive copilot, the proactive ADK digest, and the
MCP wrapper will each wrap in Phase 3 — it is neither a FastAPI module nor an MCP-native
file, so no single consumer owns the metric definitions.
"""
from .errors import SemanticError
from .layer import compare_cohorts, explain_metric, list_metrics, query_metric
from .metrics import METRICS
from .windows import Window

__all__ = [
    "SemanticError",
    "Window",
    "METRICS",
    "list_metrics",
    "query_metric",
    "compare_cohorts",
    "explain_metric",
]
