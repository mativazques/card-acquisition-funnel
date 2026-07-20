"""The digest cache (D18) — pre-generate once in Airflow, serve at $0 from BigQuery.

`mart_digest_cache` is created and upserted by THIS job, not by dbt: a dbt model would be
dropped-and-recreated on every `dbt run`, wiping past digests. So the job owns the table via
`CREATE TABLE IF NOT EXISTS` and appends one row per (cohort_month, dbt_run_id).

The honesty contract reaches all the way to the cache: `should_cache` refuses any digest the
critic rejected OR the faithfulness check failed (D11) — an invented number never lands in a
served table. Row-shaping and the gate are pure Python (tested offline); only the CREATE and
the MERGE touch BigQuery.
"""
from __future__ import annotations

import json
from typing import Any

CACHE_TABLE = "mart_digest_cache"


def should_cache(record: dict) -> bool:
    """Cache only a critic-passed AND numerically-faithful digest (D11 gate)."""
    if not record.get("critic_passed"):
        return False
    digest = record.get("digest")
    return bool(digest and digest.get("cacheable"))


def to_cache_row(record: dict, run_id: str) -> dict:
    """Shape one pipeline record into a cache row, keyed by (cohort_month, dbt_run_id)."""
    struct = record["struct"]
    digest = record["digest"]
    findings = struct.get("findings", [])
    return {
        "cohort_month": struct["cohort_month"],
        "window": struct["window"],
        "dbt_run_id": run_id,
        "prose": digest["prose"],
        "faithful": digest["faithful"],
        "material_findings": sum(1 for f in findings if f.get("material")),
        "findings_json": json.dumps(findings, ensure_ascii=False),
        "suppressed_json": json.dumps(struct.get("suppressed", []), ensure_ascii=False),
        "notes_json": json.dumps(struct.get("notes", []), ensure_ascii=False),
    }


def create_table_sql(project: str, dataset: str) -> str:
    """DDL that creates the cache table once and never drops it (idempotent, D18)."""
    return f"""
        CREATE TABLE IF NOT EXISTS `{project}.{dataset}.{CACHE_TABLE}` (
            cohort_month      STRING NOT NULL,
            metric_window     STRING NOT NULL,
            dbt_run_id        STRING NOT NULL,
            generated_at      TIMESTAMP NOT NULL,
            prose             STRING,
            faithful          BOOL,
            material_findings INT64,
            findings_json     STRING,
            suppressed_json   STRING,
            notes_json        STRING
        )
        PARTITION BY DATE(generated_at)
        CLUSTER BY cohort_month, metric_window
    """


def _merge_sql(project: str, dataset: str) -> str:
    """Upsert one row: overwrite a re-run of the same (cohort_month, dbt_run_id), else insert."""
    t = f"`{project}.{dataset}.{CACHE_TABLE}`"
    return f"""
        MERGE {t} AS target
        USING (
            SELECT
                @cohort_month AS cohort_month, @window AS metric_window, @dbt_run_id AS dbt_run_id,
                CURRENT_TIMESTAMP() AS generated_at, @prose AS prose, @faithful AS faithful,
                @material_findings AS material_findings, @findings_json AS findings_json,
                @suppressed_json AS suppressed_json, @notes_json AS notes_json
        ) AS src
        ON target.cohort_month = src.cohort_month AND target.dbt_run_id = src.dbt_run_id
        WHEN MATCHED THEN UPDATE SET
            metric_window = src.metric_window, generated_at = src.generated_at, prose = src.prose,
            faithful = src.faithful, material_findings = src.material_findings,
            findings_json = src.findings_json, suppressed_json = src.suppressed_json,
            notes_json = src.notes_json
        WHEN NOT MATCHED THEN INSERT ROW
    """


def upsert_digest(client: Any, record: dict, run_id: str, project: str, dataset: str) -> str:
    """Ensure the table exists, then MERGE one gated digest row. Returns a short status.

    Integration path (touches BigQuery). Refuses to write a digest that failed the honesty
    gate — the caller should log/flag those for human review instead.
    """
    from google.cloud import bigquery

    if not should_cache(record):
        return "skipped: digest failed the critic or faithfulness gate"

    client.query(create_table_sql(project, dataset)).result()
    row = to_cache_row(record, run_id)
    params = [
        bigquery.ScalarQueryParameter("cohort_month", "STRING", row["cohort_month"]),
        bigquery.ScalarQueryParameter("window", "STRING", row["window"]),
        bigquery.ScalarQueryParameter("dbt_run_id", "STRING", row["dbt_run_id"]),
        bigquery.ScalarQueryParameter("prose", "STRING", row["prose"]),
        bigquery.ScalarQueryParameter("faithful", "BOOL", row["faithful"]),
        bigquery.ScalarQueryParameter("material_findings", "INT64", row["material_findings"]),
        bigquery.ScalarQueryParameter("findings_json", "STRING", row["findings_json"]),
        bigquery.ScalarQueryParameter("suppressed_json", "STRING", row["suppressed_json"]),
        bigquery.ScalarQueryParameter("notes_json", "STRING", row["notes_json"]),
    ]
    job_config = bigquery.QueryJobConfig(query_parameters=params)
    client.query(_merge_sql(project, dataset), job_config=job_config).result()
    return f"cached digest for {row['cohort_month']} ({row['window']}) run={run_id}"
