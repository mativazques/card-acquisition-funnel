"""Unit tests for the deterministic planner (no LLM, no BigQuery).

The planner picks the target/prior cohorts from the fully-observed blended series and
emits the fixed set of analyst tasks the digest needs. It is plain Python — the "agentic"
value of the pipeline lives in the critic gate and the narrator, not here.
"""
from agents.planner import plan_digest, select_cohorts


def test_select_cohorts_takes_the_last_two_of_the_ascending_series():
    series = [
        {"cohort": "2015-09", "value": 0.010},
        {"cohort": "2015-10", "value": 0.0084},
        {"cohort": "2015-11", "value": 0.0052},
    ]
    assert select_cohorts(series) == ("2015-11", "2015-10")


def test_select_cohorts_needs_at_least_two_cohorts():
    try:
        select_cohorts([{"cohort": "2015-11", "value": 0.0052}])
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_plan_enumerates_blended_and_two_segment_tasks():
    plan = plan_digest(window="msa_6", cohort="2015-11", prior_cohort="2015-10")
    names = [t["name"] for t in plan["tasks"]]
    assert names == ["blended_trend", "segment_target", "segment_prior"]
    assert plan["cohort"] == "2015-11"
    assert plan["prior_cohort"] == "2015-10"
    assert plan["window"] == "msa_6"


def test_plan_tasks_call_only_the_governed_query_metric_tool():
    plan = plan_digest(window="msa_6", cohort="2015-11", prior_cohort="2015-10")
    for t in plan["tasks"]:
        assert t["tool"] == "query_metric"
        assert t["args"]["metric_id"] == "adoption_rate"
        assert t["args"]["window"] == "msa_6"
    seg = [t for t in plan["tasks"] if t["name"].startswith("segment_")]
    assert {t["args"]["cohort"] for t in seg} == {"2015-11", "2015-10"}
    assert all(t["args"]["dimension"] == "segmento" for t in seg)
