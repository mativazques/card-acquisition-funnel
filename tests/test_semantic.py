"""Unit tests for the semantic-layer contract (no BigQuery — pure validation logic)."""
import pytest

from semantic import (
    SemanticError,
    Window,
    compare_cohorts,
    explain_metric,
    list_metrics,
    query_metric,
)
from semantic.metrics import CURVES_SEG, METRICS

_MT = lambda n: f"`p.d.{n}`"  # noqa: E731 — test-only mart resolver


def test_catalog_has_the_seven_governed_metrics():
    ids = {m["id"] for m in list_metrics()}
    assert ids == {
        "cohort_size",
        "adoption_rate",
        "adoption_rate_segment_adjusted",
        "time_to_adoption",
        "retention_rate",
        "funnel_conversion",
        "segment_mix",
    }


def test_list_metrics_exposes_compositional_flag():
    by_id = {m["id"]: m for m in list_metrics()}
    assert by_id["segment_mix"]["compositional"] is True
    assert by_id["adoption_rate"]["compositional"] is False


def test_unknown_metric_is_structured_error():
    with pytest.raises(SemanticError) as exc:
        query_metric("made_up_metric")
    assert exc.value.code == "metric_unknown"
    assert "error" in exc.value.as_dict()


def test_unknown_window_is_structured_error():
    with pytest.raises(SemanticError) as exc:
        query_metric("adoption_rate", window="msa_99")
    assert exc.value.code == "window_unknown"


def test_window_not_valid_for_metric_is_rejected():
    # cohort_size is a lifetime count — no msa window.
    with pytest.raises(SemanticError) as exc:
        query_metric("cohort_size", window="msa_6")
    assert exc.value.code == "window_unsupported"


def test_adoption_rate_windows():
    m = METRICS["adoption_rate"]
    for good in (Window.MSA_3, Window.MSA_6, Window.MSA_12):
        assert m.supports(good)
    for bad in ("lifetime", "ret_1m"):
        with pytest.raises(SemanticError) as exc:
            query_metric("adoption_rate", window=bad)
        assert exc.value.code == "window_unsupported"


def test_adoption_rate_sql_filters_observed_cells():
    sql = METRICS["adoption_rate"].build_sql(Window.MSA_6, _MT)
    assert "msa = 6" in sql
    assert "is_cell_right_censored = false" in sql
    assert "mart_adoption_curves" in sql


def test_segment_adjusted_reweights_over_segment_mart():
    sql = METRICS["adoption_rate_segment_adjusted"].build_sql(Window.MSA_6, _MT)
    assert CURVES_SEG in sql
    # holds mix constant via a reference-weight CTE and renormalizes on sum(w)
    assert "ref_w" in sql and "over ()" in sql
    assert "msa = 6" in sql


def test_retention_rate_maps_window_to_column():
    assert "retention_rate_1m" in METRICS["retention_rate"].build_sql(Window.RET_1M, _MT)
    assert "retention_rate_3m" in METRICS["retention_rate"].build_sql(Window.RET_3M, _MT)


def test_funnel_conversion_windows_use_distinct_numerators():
    acq = METRICS["funnel_conversion"].build_sql(Window.ACQUIRED_TO_ADOPTED, _MT)
    ret = METRICS["funnel_conversion"].build_sql(Window.ADOPTED_TO_RETAINED, _MT)
    assert "retained_3m" not in acq
    assert "retained_3m" in ret


def test_segment_mix_is_compositional_and_not_comparable():
    assert METRICS["segment_mix"].compositional is True
    with pytest.raises(SemanticError) as exc:
        compare_cohorts("2015-01", "2015-02", "segment_mix")
    assert exc.value.code == "metric_not_comparable"


def test_explain_metric_returns_windows_and_caveats():
    info = explain_metric("adoption_rate_segment_adjusted")
    assert info["valid_windows"] == ["msa_3", "msa_6", "msa_12"]
    assert info["caveats"], "segment-adjusted metric must carry honesty caveats"


def test_explain_metric_unknown_is_structured_error():
    with pytest.raises(SemanticError) as exc:
        explain_metric("nope")
    assert exc.value.code == "metric_unknown"


# --- D17: per-segment access via query_metric(dimension="segmento") ----------------

def test_adoption_rate_exposes_a_segment_builder():
    # The by-segment analyst slice and the min-n guard both need per-cell value + n.
    assert METRICS["adoption_rate"].build_segment_sql is not None


def test_adoption_rate_by_segment_sql_returns_value_and_n_per_cell():
    sql = METRICS["adoption_rate"].build_segment_sql(Window.MSA_6, _MT)
    assert CURVES_SEG in sql          # reads the acq_month x segmento x msa mart
    assert "msa = 6" in sql
    assert "is_cell_right_censored = false" in sql
    assert " as segment" in sql       # segment dimension surfaced
    assert " as value" in sql         # adoption_rate as the value
    assert " as n" in sql             # n_observed surfaced for the min-n guard


def test_scalar_metric_has_no_segment_builder():
    assert METRICS["cohort_size"].build_segment_sql is None


def test_query_metric_rejects_unknown_dimension():
    with pytest.raises(SemanticError) as exc:
        query_metric("adoption_rate", window="msa_6", dimension="planet")
    assert exc.value.code == "dimension_unknown"


def test_query_metric_rejects_segment_dimension_on_unsupported_metric():
    with pytest.raises(SemanticError) as exc:
        query_metric("cohort_size", dimension="segmento")
    assert exc.value.code == "dimension_unsupported"
