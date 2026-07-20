"""The Airflow-facing digest job: generate one digest, then cache it — post-dbt (D4/D18).

The DAG runs this AFTER `dbt run + dbt test`, so the digest always reflects freshly-tested
marts. It generates the digest against live BigQuery + Gemini, then writes it to
`mart_digest_cache` ONLY if it passed the critic and the numeric-faithfulness gate. An
unfaithful or critic-rejected digest is logged for human review and never served.

`run_id` is the Airflow run id, so re-running a cohort upserts (idempotent) rather than
piling duplicate rows. Requires GEMINI_API_KEY (AI Studio free tier) or the Vertex toggle.
"""
from __future__ import annotations

import logging
import os

from dotenv import load_dotenv

from agents.digest_cache import should_cache, upsert_digest
from agents.narrator import genai_generator
from agents.pipeline import run_digest
from agents.tools import TOOL_FUNCTIONS

log = logging.getLogger(__name__)


def run_and_cache(run_id: str, window: str = "msa_6", cohort: str | None = None,
                  prior_cohort: str | None = None) -> str:
    """Generate one digest and upsert it into the cache if it passes the honesty gate."""
    load_dotenv()
    project = os.environ.get("GCP_PROJECT", "card-acquisition-funnel-2026")
    dataset = f"{os.environ.get('BQ_DBT_DATASET', 'analytics')}_marts"

    record = run_digest(
        tools=TOOL_FUNCTIONS,
        generate=genai_generator(),
        window=window,
        cohort=cohort,
        prior_cohort=prior_cohort,
    )

    if not should_cache(record):
        if not record["critic_passed"]:
            log.warning("digest rejected by critic gate: %s", record["struct"].get("suppressed"))
            return "not cached: critic gate rejected the cohort"
        log.warning(
            "digest failed numeric-faithfulness — flagged for review; violations=%s",
            record["digest"]["violations"],
        )
        return "not cached: failed faithfulness gate (flagged for review)"

    from google.cloud import bigquery

    client = bigquery.Client(project=project)
    status = upsert_digest(client, record, run_id, project, dataset)
    log.info(status)
    return status


def main() -> None:
    import argparse

    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Generate and cache one proactive digest.")
    parser.add_argument("--run-id", required=True, help="Airflow run id (cache upsert key).")
    parser.add_argument("--window", default="msa_6")
    parser.add_argument("--cohort", default=None)
    parser.add_argument("--prior-cohort", default=None)
    args = parser.parse_args()
    print(run_and_cache(args.run_id, args.window, args.cohort, args.prior_cohort))


if __name__ == "__main__":
    main()
