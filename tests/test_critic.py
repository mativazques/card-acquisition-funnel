"""Unit tests for the deterministic critic guards (no LLM, no BigQuery).

These three guards (D10) are the project's honesty gate. They are CODE, not model judgment,
so they must be pinned by tests: right-censoring suppression, min-n=50 suppression, and the
two-part materiality gate (abs >= 2pp AND > 1.5x rolling SD, with a 2pp-only fallback when
there is not enough cohort history to estimate the SD).
"""
from agents.critic import (
    MATERIALITY_ABS,
    MIN_N,
    apply_min_n,
    assess_materiality,
    consecutive_deltas,
    critique,
    is_fully_observed,
)


# --- Guard 1: right-censoring ------------------------------------------------------

def test_fully_observed_reads_the_flag_map():
    flags = {"2015-10": True, "2015-11": True, "2016-01": False}
    assert is_fully_observed("2015-11", flags) is True
    assert is_fully_observed("2016-01", flags) is False


def test_unknown_cohort_is_not_treated_as_observed():
    assert is_fully_observed("2099-01", {"2015-10": True}) is False


# --- Guard 2: min-n = 50 -----------------------------------------------------------

def test_min_n_passes_a_large_cell_untouched():
    cell = {"segment": "02 - PARTICULARES", "value": 0.0133, "n": 2704}
    assert apply_min_n(cell) == cell


def test_min_n_suppresses_a_small_cell_with_a_structured_token():
    out = apply_min_n({"segment": "unknown", "value": 0.0, "n": 12})
    assert out["suppressed"] is True
    assert out["reason"] == "min_n"
    assert out["n"] == 12
    assert "value" not in out  # the value must not leak past suppression


def test_min_n_threshold_is_fifty():
    assert MIN_N == 50
    assert apply_min_n({"segment": "x", "value": 0.1, "n": 49})["suppressed"] is True
    assert apply_min_n({"segment": "x", "value": 0.1, "n": 50}).get("suppressed") is None


# --- Guard 3: materiality ----------------------------------------------------------

def test_materiality_absolute_threshold_is_two_pp():
    assert MATERIALITY_ABS == 0.02


def test_delta_below_two_pp_is_never_material():
    v = assess_materiality(-0.015, prior_deltas=[0.001, 0.0, -0.002])
    assert v["material"] is False


def test_delta_over_two_pp_and_over_sd_band_is_material():
    # prior deltas tiny (sd ~ 0.001), a -3pp move is both >= 2pp and >> 1.5x sd
    v = assess_materiality(-0.03, prior_deltas=[0.001, 0.0, -0.001])
    assert v["material"] is True
    assert v["insufficient_history"] is False


def test_delta_over_two_pp_but_within_noise_band_is_not_material():
    # prior deltas are volatile (sd large), so a -3pp move is within 1.5x sd -> not material
    v = assess_materiality(-0.03, prior_deltas=[0.05, -0.05, 0.04])
    assert v["material"] is False
    assert v["sd"] is not None and v["threshold_sd"] > 0.03


def test_fewer_than_three_prior_deltas_falls_back_to_absolute_only():
    v = assess_materiality(-0.03, prior_deltas=[0.001])
    assert v["material"] is True
    assert v["insufficient_history"] is True
    assert v["sd"] is None


def test_consecutive_deltas_pairs_each_cohort_with_its_predecessor():
    series = [
        {"cohort": "2015-08", "value": 0.010},
        {"cohort": "2015-09", "value": 0.008},
        {"cohort": "2015-10", "value": 0.005},
    ]
    deltas = consecutive_deltas(series)
    assert deltas[0] == {"cohort": "2015-09", "prior_cohort": "2015-08", "delta": -0.002}
    assert deltas[1]["cohort"] == "2015-10"
    assert round(deltas[1]["delta"], 4) == -0.003


# --- The composed critic struct ----------------------------------------------------

def test_critique_suppresses_small_segment_cells_and_keeps_big_ones():
    out = critique(
        window="msa_6",
        cohort="2015-11",
        prior_cohort="2015-10",
        blended_series=[
            {"cohort": "2015-08", "value": 0.012},
            {"cohort": "2015-09", "value": 0.010},
            {"cohort": "2015-10", "value": 0.0084},
            {"cohort": "2015-11", "value": 0.0052},
        ],
        target_cells=[
            {"segment": "02 - PARTICULARES", "value": 0.008, "n": 2704},
            {"segment": "unknown", "value": 0.0, "n": 12},
        ],
        prior_cells=[
            {"segment": "02 - PARTICULARES", "value": 0.013, "n": 2600},
            {"segment": "unknown", "value": 0.0, "n": 9},
        ],
        fully_observed_map={"2015-10": True, "2015-11": True},
    )
    seg_findings = {f["segment"] for f in out["findings"] if f["kind"] == "segment_delta"}
    assert "02 - PARTICULARES" in seg_findings
    suppressed = {(s["reason"], s["segment"]) for s in out["suppressed"]}
    assert ("min_n", "unknown") in suppressed


def test_critique_refuses_a_right_censored_target_cohort():
    out = critique(
        window="msa_6",
        cohort="2016-03",
        prior_cohort="2016-02",
        blended_series=[{"cohort": "2016-02", "value": 0.01}],
        target_cells=[],
        prior_cells=[],
        fully_observed_map={"2016-02": True, "2016-03": False},
    )
    assert out["critic_passed"] is False
    assert any(s["reason"] == "right_censored" for s in out["suppressed"])
