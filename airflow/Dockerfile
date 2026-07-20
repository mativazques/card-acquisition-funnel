FROM quay.io/astronomer/astro-runtime:12.7.1

# dbt runs in an ISOLATED virtualenv, not the Airflow environment. dbt-core and
# Airflow pin conflicting versions of shared deps (e.g. jinja2, protobuf), so
# installing dbt-bigquery into the Airflow env makes pip's resolver explode
# (ResolutionTooDeep). Cosmos executes dbt from this venv via the DAG's
# ExecutionConfig(dbt_executable_path=...). This is Astronomer's recommended pattern.
RUN python -m venv /usr/local/airflow/dbt_venv && \
    /usr/local/airflow/dbt_venv/bin/pip install --no-cache-dir dbt-bigquery==1.9.2 && \
    /usr/local/airflow/dbt_venv/bin/dbt --version

# The proactive-digest job runs in its OWN venv too — same isolation reason as dbt.
# The digest path uses google-genai directly (a single stateless narrator call), NOT
# google-adk, so this venv stays light: no protobuf war with the Airflow env. The
# digest DAG task shells to this python (see the BashOperator in the DAG).
RUN python -m venv /usr/local/airflow/agents_venv && \
    /usr/local/airflow/agents_venv/bin/pip install --no-cache-dir \
        google-genai==1.46.0 google-cloud-bigquery==3.27.0 python-dotenv==1.0.1 && \
    /usr/local/airflow/agents_venv/bin/python -c "from google import genai; print('agents_venv ok')"
