# Airflow orchestration (Phase 1)

Local Airflow (Astronomer Runtime + [Cosmos](https://astronomer.github.io/astronomer-cosmos/))
that runs the card-acquisition pipeline end to end:

```
ingest (Kaggle -> GCS -> BigQuery)  ->  dbt run + dbt test  (per model, via Cosmos)
```

Cosmos renders **each dbt model as its own Airflow task** with its data tests right
after it (`TestBehavior.AFTER_EACH`), so the DAG mirrors the real dbt lineage instead
of hiding it behind a single `BashOperator dbt run`. See `dags/card_acquisition_pipeline.py`.

## One source of truth

The dbt project (`../dbt`) and the ingestion script (`../scripts`) are **bind-mounted**
into the containers (see `docker-compose.override.yml`) — they are not copied into the
image. There is one dbt project in the repo, used identically whether you run dbt by
hand or through Airflow.

dbt runs in an **isolated virtualenv inside the image** (`/usr/local/airflow/dbt_venv`,
built in the `Dockerfile`). dbt-core and Airflow pin conflicting shared dependencies, so
installing them together breaks pip's resolver — the venv keeps them apart, and Cosmos
executes dbt from it via `ExecutionConfig(dbt_executable_path=...)`.

BigQuery auth reuses your local ADC (`gcloud auth application-default login`), mounted
read-only — no service-account key on disk. `GCP_*` env vars come from the repo `.env`.

## Run it

```bash
make airflow-start     # cd airflow && astro dev start  (needs Docker + the Astro CLI)
# open http://localhost:8080  (admin / admin), un-pause `card_acquisition_pipeline`, trigger it
make airflow-stop
```

Requirements: [Docker](https://www.docker.com/) and the
[Astro CLI](https://www.astronomer.io/docs/astro/cli/install-cli) (`brew install astro`).

## Honest framing

On the static Santander panel this batch runs **once** (`schedule=None`). It is
written for incremental ingestion — schedule it `@daily` in production — and included as
a production-readiness demonstration, not because the public dataset changes daily.
