"""Card Acquisition Funnel — batch pipeline (Phases 1 & 3).

    ingest (Kaggle -> GCS -> BigQuery)  ->  dbt run + dbt test  (via Cosmos)
    ->  generate_digest (proactive multi-agent digest, cached at $0)

Cosmos renders EACH dbt model as its own Airflow task (with its tests right after),
so the DAG mirrors the dbt lineage instead of hiding it behind a single
`BashOperator dbt run`. The dbt project and the ingest script are bind-mounted from
the repo (see docker-compose.override.yml) — one source of truth, no duplication.

After the marts are built AND tested, `generate_digest` runs the proactive pipeline
(planner -> parallel analysts -> deterministic critic gate -> narrator) for the latest
fully-observed cohort and upserts the critic-gated, numerically-faithful result into
`mart_digest_cache`. Serving from that cache keeps the Streamlit "Insight of the month"
panel at $0. The digest runs in its own light venv (google-genai, not google-adk).

Honest framing: on the static Santander panel this batch runs once. It is written
for incremental ingestion (schedule it @daily in production) and included as a
production-readiness demonstration.

Run it locally: `cd airflow && astro dev start` (needs Docker + the Astro CLI), then
trigger `card_acquisition_pipeline` from the Airflow UI at http://localhost:8080.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from airflow import DAG
from airflow.operators.bash import BashOperator
from cosmos import (
    DbtTaskGroup,
    ExecutionConfig,
    ProfileConfig,
    ProjectConfig,
    RenderConfig,
)
from cosmos.constants import LoadMode, TestBehavior

# Paths inside the Airflow containers (bind-mounted from the repo).
AIRFLOW_HOME = Path("/usr/local/airflow")
DBT_PROJECT_DIR = AIRFLOW_HOME / "dbt"
INGEST_SCRIPT = "/usr/local/airflow/scripts/ingest.py"

# The digest job runs in its own light venv (see Dockerfile); the agents/semantic
# packages are bind-mounted, so PYTHONPATH points at the Airflow home to import them.
AGENTS_PYTHON = "/usr/local/airflow/agents_venv/bin/python"

# dbt lives in its own venv (see Dockerfile) — Airflow and dbt can't share one
# environment without a dependency conflict. Cosmos shells out to this binary.
DBT_EXECUTABLE = "/usr/local/airflow/dbt_venv/bin/dbt"

# Reuse the dbt project's own env-driven profiles.yml (oauth/ADC), same as running
# dbt locally. The container gets ADC via the mounted ~/.config/gcloud and the
# GCP_* env vars from the repo .env (both wired in docker-compose.override.yml).
profile_config = ProfileConfig(
    profile_name="card_acquisition_funnel",
    target_name="dev",
    profiles_yml_filepath=DBT_PROJECT_DIR / "profiles.yml",
)

project_config = ProjectConfig(dbt_project_path=DBT_PROJECT_DIR)

execution_config = ExecutionConfig(dbt_executable_path=DBT_EXECUTABLE)

# One task per model, each followed by its data tests -> the classic
# "dbt run then dbt test" gate, but per-model with real lineage. DBT_LS parses the
# graph offline at DAG-load time (via the venv dbt), so no warehouse connection is
# needed just to render the tasks.
render_config = RenderConfig(
    test_behavior=TestBehavior.AFTER_EACH,
    load_method=LoadMode.DBT_LS,
    dbt_executable_path=DBT_EXECUTABLE,
)

with DAG(
    dag_id="card_acquisition_pipeline",
    start_date=datetime(2024, 1, 1),
    schedule=None,  # @daily in production; static dataset runs on demand here
    catchup=False,
    tags=["card-acquisition", "dbt", "bigquery"],
) as dag:

    ingest = BashOperator(
        task_id="ingest",
        bash_command=f"python {INGEST_SCRIPT}",
    )

    transform = DbtTaskGroup(
        group_id="dbt",
        project_config=project_config,
        profile_config=profile_config,
        render_config=render_config,
        execution_config=execution_config,
    )

    # Proactive digest, post-dbt: generate for the latest fully-observed cohort and upsert
    # into mart_digest_cache. Keyed by {{ run_id }} so a re-run upserts instead of duplicating.
    # The honesty gate lives in the job: only a critic-passed, numerically-faithful digest
    # is cached; anything else is logged for human review and skipped.
    generate_digest = BashOperator(
        task_id="generate_digest",
        bash_command=(
            f"PYTHONPATH={AIRFLOW_HOME} {AGENTS_PYTHON} -m agents.digest_job "
            '--run-id "{{ run_id }}" --window msa_6'
        ),
    )

    ingest >> transform >> generate_digest
