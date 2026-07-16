FROM quay.io/astronomer/astro-runtime:12.7.1

# dbt runs in an ISOLATED virtualenv, not the Airflow environment. dbt-core and
# Airflow pin conflicting versions of shared deps (e.g. jinja2, protobuf), so
# installing dbt-bigquery into the Airflow env makes pip's resolver explode
# (ResolutionTooDeep). Cosmos executes dbt from this venv via the DAG's
# ExecutionConfig(dbt_executable_path=...). This is Astronomer's recommended pattern.
RUN python -m venv /usr/local/airflow/dbt_venv && \
    /usr/local/airflow/dbt_venv/bin/pip install --no-cache-dir dbt-bigquery==1.9.2 && \
    /usr/local/airflow/dbt_venv/bin/dbt --version
