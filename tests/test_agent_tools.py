"""Unit tests for the agent tools edge (no BigQuery — wrapping + declarations only).

The edge wraps the four governed semantic tools so every agent path (reactive copilot,
proactive ADK digest, MCP wrapper) speaks one contract: a SemanticError becomes structured
error-as-data instead of an exception the LLM runtime cannot catch, and each tool ships a
Gemini-style function declaration.
"""
import pytest

from agents.tools import (
    TOOL_DECLARATIONS,
    TOOL_FUNCTIONS,
    tool_compare_cohorts,
    tool_explain_metric,
    tool_list_metrics,
    tool_query_metric,
)


def test_tool_list_metrics_passes_through_the_seven_metrics():
    ids = {m["id"] for m in tool_list_metrics()}
    assert len(ids) == 7 and "adoption_rate" in ids


def test_contract_violation_returns_error_as_data_not_raise():
    out = tool_query_metric("made_up_metric")
    assert out["error"]["code"] == "metric_unknown"


def test_unknown_dimension_returns_error_as_data():
    out = tool_query_metric("adoption_rate", window="msa_6", dimension="planet")
    assert out["error"]["code"] == "dimension_unknown"


def test_declarations_cover_exactly_the_four_governed_tools():
    names = {d["name"] for d in TOOL_DECLARATIONS}
    assert names == {"list_metrics", "query_metric", "compare_cohorts", "explain_metric"}


def test_query_metric_declaration_exposes_the_dimension_param():
    decl = next(d for d in TOOL_DECLARATIONS if d["name"] == "query_metric")
    assert "dimension" in decl["parameters"]["properties"]


def test_every_declaration_has_a_matching_callable():
    for d in TOOL_DECLARATIONS:
        assert d["name"] in TOOL_FUNCTIONS


def test_tool_signatures_are_parseable_by_adk_automatic_function_calling():
    # Regression: ADK's automatic function calling rejects `str | None` unions — a copilot
    # turn raised at request time and returned an empty answer. Guard the signatures directly.
    FunctionTool = pytest.importorskip("google.adk.tools.function_tool").FunctionTool
    for fn in (tool_list_metrics, tool_query_metric, tool_compare_cohorts, tool_explain_metric):
        FunctionTool(fn)._get_declaration()  # raises ValueError on an unparseable signature
