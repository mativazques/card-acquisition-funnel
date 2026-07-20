"""Unit tests for the digest-cache shaping and the caching gate (no BigQuery).

The digest is pre-generated in Airflow and served from `mart_digest_cache` so serve-time
cost stays $0 (D4/D18). Two rules are pure Python and must be pinned by tests:
  - only a critic-passed AND numerically-faithful digest may be cached (D11 gate);
  - the cache row is shaped losslessly from the pipeline record, keyed by (cohort, run id).
The `CREATE TABLE IF NOT EXISTS` / MERGE execution against BigQuery is integration, not here.
"""
import json

from agents.digest_cache import CACHE_TABLE, should_cache, to_cache_row


def _passed_record(cacheable=True):
    return {
        "critic_passed": True,
        "struct": {
            "cohort_month": "2015-11",
            "window": "msa_6",
            "findings": [
                {"kind": "blended_delta", "delta": -0.0032, "material": True},
                {"kind": "segment_delta", "segment": "01 - TOP", "delta": -0.004, "material": False},
            ],
            "suppressed": [{"reason": "min_n", "segment": "unknown", "n": 12}],
            "notes": ["insufficient history for materiality assessment"],
        },
        "digest": {
            "prose": "The 2015-11 cohort fell 0.32pp.",
            "faithful": cacheable,
            "violations": [] if cacheable else ["0.19%"],
            "cacheable": cacheable,
        },
    }


def test_cache_table_name_is_stable():
    assert CACHE_TABLE == "mart_digest_cache"


def test_should_cache_only_a_passed_and_faithful_digest():
    assert should_cache(_passed_record(cacheable=True)) is True
    assert should_cache(_passed_record(cacheable=False)) is False


def test_should_not_cache_a_critic_rejected_digest():
    rejected = {"critic_passed": False, "struct": {"cohort_month": "2016-03"}, "digest": None}
    assert should_cache(rejected) is False


def test_to_cache_row_shapes_the_record_losslessly():
    row = to_cache_row(_passed_record(), run_id="manual__2026-07-17T00:00:00")
    assert row["cohort_month"] == "2015-11"
    assert row["window"] == "msa_6"
    assert row["dbt_run_id"] == "manual__2026-07-17T00:00:00"
    assert row["prose"] == "The 2015-11 cohort fell 0.32pp."
    assert row["faithful"] is True
    assert row["material_findings"] == 1  # only the blended_delta is material
    assert json.loads(row["findings_json"])[0]["kind"] == "blended_delta"
    assert json.loads(row["suppressed_json"])[0]["segment"] == "unknown"
    assert json.loads(row["notes_json"]) == ["insufficient history for materiality assessment"]
