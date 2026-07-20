"""Thin MCP wrapper — exposes the four governed tools to any MCP client (D7, D15).

This adds NO new metric logic: each MCP tool wraps the corresponding governed callable from
`agents.tools` one-to-one, so the same error-as-data contract, semantic governance, and
honesty caveats carry over unchanged. An MCP client (Claude Desktop, an IDE, another agent)
gets exactly the text-to-metric surface the copilot and the digest use — never raw SQL.

Run as a stdio MCP server:  .venv-agents/bin/python -m agents.mcp_server
"""
from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from agents.tools import (
    tool_compare_cohorts,
    tool_explain_metric,
    tool_list_metrics,
    tool_query_metric,
)


def build_mcp_server() -> FastMCP:
    """Register the four governed tools on a FastMCP server and return it."""
    mcp = FastMCP("card-acquisition-funnel")

    @mcp.tool()
    def list_metrics() -> Any:
        """List every governed metric and the windows each supports."""
        return tool_list_metrics()

    @mcp.tool()
    def query_metric(
        metric_id: str,
        window: str = "lifetime",
        cohort: str | None = None,
        dimension: str | None = None,
    ) -> Any:
        """Resolve a governed metric to per-cohort values (dimension='segmento' for per-segment cells)."""
        return tool_query_metric(metric_id, window, cohort, dimension)

    @mcp.tool()
    def compare_cohorts(
        cohort_a: str,
        cohort_b: str,
        metric_id: str,
        window: str = "lifetime",
    ) -> Any:
        """Compare one scalar governed metric between two cohorts at one window."""
        return tool_compare_cohorts(cohort_a, cohort_b, metric_id, window)

    @mcp.tool()
    def explain_metric(metric_id: str) -> Any:
        """Return one metric's definition, valid windows, and honesty caveats."""
        return tool_explain_metric(metric_id)

    return mcp


if __name__ == "__main__":
    build_mcp_server().run()
