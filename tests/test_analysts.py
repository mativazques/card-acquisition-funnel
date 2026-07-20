"""Unit tests for the analyst stage (no LLM, no BigQuery).

The analyst stage executes the planner's independent tasks against the governed tools
(injected as a dict of callables, so tests need no BigQuery) and reshapes the results into
the exact inputs the deterministic critic consumes. A tool that returns error-as-data
(never raises) must surface as a structured failure, not a crash.
"""
from agents.analysts import run_analysts, to_critic_inputs
from agents.planner import plan_digest


def _fake_tools():
    def query_metric(metric_id, window, cohort=None, dimension=None):
        if dimension == "segmento":
            cells = {
                "2015-11": [
                    {"cohort": "2015-11", "segment": "02 - PARTICULARES", "value": 0.008, "n": 2704},
                    {"cohort": "2015-11", "segment": "unknown", "value": 0.0, "n": 12},
                ],
                "2015-10": [
                    {"cohort": "2015-10", "segment": "02 - PARTICULARES", "value": 0.013, "n": 2600},
                ],
            }[cohort]
            return {"metric": metric_id, "window": window, "dimension": "segmento", "results": cells}
        return {
            "metric": metric_id,
            "window": window,
            "dimension": None,
            "results": [
                {"cohort": "2015-10", "value": 0.0084},
                {"cohort": "2015-11", "value": 0.0052},
            ],
        }

    return {"query_metric": query_metric}


def test_run_analysts_executes_every_task_by_name():
    plan = plan_digest(window="msa_6", cohort="2015-11", prior_cohort="2015-10")
    out = run_analysts(plan, tools=_fake_tools())
    assert set(out) == {"blended_trend", "segment_target", "segment_prior"}
    assert out["blended_trend"]["results"][-1]["cohort"] == "2015-11"


def test_to_critic_inputs_reshapes_series_and_cells():
    plan = plan_digest(window="msa_6", cohort="2015-11", prior_cohort="2015-10")
    out = run_analysts(plan, tools=_fake_tools())
    series, target_cells, prior_cells = to_critic_inputs(out)
    assert series[-1] == {"cohort": "2015-11", "value": 0.0052}
    assert {"segment": "02 - PARTICULARES", "value": 0.008, "n": 2704} in target_cells
    assert {"segment": "unknown", "value": 0.0, "n": 12} in target_cells
    assert prior_cells == [{"segment": "02 - PARTICULARES", "value": 0.013, "n": 2600}]


def test_tool_error_as_data_surfaces_as_a_failed_task():
    def broken_tools():
        def query_metric(metric_id, window, cohort=None, dimension=None):
            return {"error": {"code": "dimension_unsupported", "message": "nope"}}

        return {"query_metric": query_metric}

    plan = plan_digest(window="msa_6", cohort="2015-11", prior_cohort="2015-10")
    out = run_analysts(plan, tools=broken_tools())
    try:
        to_critic_inputs(out)
        assert False, "expected a structured failure on tool error"
    except ValueError as exc:
        assert "dimension_unsupported" in str(exc)
