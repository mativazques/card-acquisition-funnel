"""Runtime configuration for the card-acquisition-funnel Streamlit app.

Reads the same env the dbt/ingest layers use (loaded from .env locally, or the
Cloud Run environment in production) so there is a single source of truth for the
GCP project and where the marts live.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from google.cloud import bigquery

# Load .env from repo root (one level up from app/)
_repo_root = Path(__file__).resolve().parent.parent
load_dotenv(_repo_root / ".env")

# dbt writes marts to `<BQ_DBT_DATASET>_<schema>`; the marts schema is "marts".
_DBT_DATASET = os.environ.get("BQ_DBT_DATASET", "analytics")
MARTS_DATASET = f"{_DBT_DATASET}_marts"

GCP_PROJECT = os.environ.get("GCP_PROJECT", "card-acquisition-funnel-2026")


def marts_table(name: str) -> str:
    """Fully-qualified `project.dataset.table` for a mart."""
    return f"`{GCP_PROJECT}.{MARTS_DATASET}.{name}`"


@lru_cache(maxsize=1)
def get_client() -> bigquery.Client:
    """A process-wide BigQuery client (ADC auth, same as dbt)."""
    return bigquery.Client(project=GCP_PROJECT)
