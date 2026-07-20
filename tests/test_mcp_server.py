"""Tests for the thin MCP wrapper (no LLM, no network).

The MCP server exposes the SAME four governed tools (D7) to any MCP client, wrapping them
one-to-one — no new metric logic, so honesty and reproducibility carry over for free. We
verify the four tools register and that a tool call routes through the governed edge
(error-as-data, never a raised exception).
"""
import asyncio

from agents.mcp_server import build_mcp_server


def test_the_four_governed_tools_are_registered():
    server = build_mcp_server()
    names = {t.name for t in asyncio.run(server.list_tools())}
    assert names == {"list_metrics", "query_metric", "compare_cohorts", "explain_metric"}


def test_a_tool_call_returns_error_as_data_not_an_exception():
    server = build_mcp_server()
    # explain_metric on an unknown metric must come back as a structured error dict,
    # never raise — an MCP client cannot catch a Python exception.
    result = asyncio.run(server.call_tool("explain_metric", {"metric_id": "not_a_metric"}))
    text = str(result)
    assert "metric_unknown" in text
