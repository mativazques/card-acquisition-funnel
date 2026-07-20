"""End-to-end test of the proactive digest pipeline (no live LLM, no BigQuery).

planner -> analysts -> deterministic critic gate -> narrator. The tools and the LLM are
both injected, so this exercises the real wiring offline: cohort auto-selection, the critic
gate short-circuit on a right-censored target, and the faithfulness gate on the narration.
"""
from agents.pipeline import run_digest


def _fake_tools(series):
    seg = {
        "2015-11": [
            {"cohort": "2015-11", "segment": "02 - PARTICULARES", "value": 0.0052, "n": 2704},
            {"cohort": "2015-11", "segment": "unknown", "value": 0.0, "n": 12},
        ],
        "2015-10": [
            {"cohort": "2015-10", "segment": "02 - PARTICULARES", "value": 0.0084, "n": 2600},
        ],
    }

    def query_metric(metric_id, window, cohort=None, dimension=None):
        if dimension == "segmento":
            return {"results": seg.get(cohort, [])}
        return {"results": series}

    return {"query_metric": query_metric}


def test_pipeline_auto_selects_last_two_cohorts_and_narrates():
    series = [
        {"cohort": "2015-08", "value": 0.012},
        {"cohort": "2015-09", "value": 0.010},
        {"cohort": "2015-10", "value": 0.0084},
        {"cohort": "2015-11", "value": 0.0052},
    ]
    prose = "The 2015-11 cohort's blended adoption fell to 0.52% from 0.84%, a 0.32pp drop."
    out = run_digest(tools=_fake_tools(series), generate=lambda _p: prose, window="msa_6")
    assert out["critic_passed"] is True
    assert out["struct"]["cohort_month"] == "2015-11"
    assert out["digest"]["faithful"] is True
    assert out["digest"]["cacheable"] is True


def test_pipeline_refuses_a_right_censored_target_without_calling_the_llm():
    # target 2016-03 is NOT in the fully-observed series -> critic Guard 1 fails
    series = [{"cohort": "2016-01", "value": 0.01}, {"cohort": "2016-02", "value": 0.009}]

    def exploding_generate(_prompt):
        raise AssertionError("narrator must not run when the critic gate fails")

    out = run_digest(
        tools=_fake_tools(series),
        generate=exploding_generate,
        window="msa_6",
        cohort="2016-03",
        prior_cohort="2016-02",
    )
    assert out["critic_passed"] is False
    assert out["digest"] is None
    assert any(s["reason"] == "right_censored" for s in out["struct"]["suppressed"])


def test_pipeline_flags_unfaithful_narration_as_non_cacheable():
    series = [
        {"cohort": "2015-09", "value": 0.010},
        {"cohort": "2015-10", "value": 0.0084},
        {"cohort": "2015-11", "value": 0.0052},
    ]
    prose = "Adoption cratered to 0.19% because of a pricing change."
    out = run_digest(tools=_fake_tools(series), generate=lambda _p: prose, window="msa_6")
    assert out["critic_passed"] is True
    assert out["digest"]["cacheable"] is False
    assert "0.19%" in out["digest"]["violations"]
