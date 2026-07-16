# Card-Acquisition Funnel — operational targets.
# Loads .env if present so GCP/Kaggle vars are available to the recipes.
ifneq (,$(wildcard .env))
include .env
export
endif

# Interpreter: defaults to python3; override to use a venv, e.g. `make hydrate PYTHON=.venv/bin/python`.
PYTHON ?= python3
DBT ?= .venv/bin/dbt
DBT_DIR := dbt
# The Streamlit app has its own venv: streamlit pins protobuf<6 while dbt needs >=6,
# so they cannot share an environment. Create it with:
#   python3 -m venv .venv-app && .venv-app/bin/pip install -r app/requirements.txt
APP_PYTHON ?= .venv-app/bin/python
# The copilot (FastAPI + Gemini + ADK) has its own venv — google-genai + fastapi.
# Create it with:
#   python3 -m venv .venv-copilot && .venv-copilot/bin/pip install -r copilot/requirements.txt
COPILOT_PYTHON ?= .venv-copilot/bin/python
# The MCP server needs its own venv: MCP SDK requires Python >=3.10. Create with:
#   python3.12 -m venv .venv-mcp && .venv-mcp/bin/pip install -r copilot/requirements-mcp.txt
MCP_PYTHON ?= .venv-mcp/bin/python
# dbt reads GCP_PROJECT / BQ_DBT_DATASET / BQ_LOCATION from the exported .env above.
export DBT_PROFILES_DIR := $(abspath dbt)

# Deploy: Terraform owns the serving layer; the image lands in Artifact Registry.
TF_DIR := terraform
GCP_REGION ?= us-central1
AR_IMAGE := $(GCP_REGION)-docker.pkg.dev/$(GCP_PROJECT)/funnel/card-acquisition-funnel:latest
TF := terraform -chdir=$(TF_DIR)
TF_VARS := -var project_id=$(GCP_PROJECT) -var region=$(GCP_REGION) -var bq_dbt_dataset=$(BQ_DBT_DATASET)

.DEFAULT_GOAL := help
.PHONY: help hydrate app api mcp copilot-test mcp-test docker-build tf-init tf-bootstrap secret-push image-push deploy trim teardown dbt-debug dbt-run dbt-test dbt-build dbt-docs airflow-start airflow-stop

help:
	@echo "hydrate        - ingest Kaggle competition -> GCS -> BQ, then build + test dbt models"
	@echo "dbt-debug      - check dbt connects to BigQuery"
	@echo "dbt-run        - build dbt models        (SELECT=name to target one)"
	@echo "dbt-test       - run dbt data tests       (SELECT=... optional)"
	@echo "dbt-build      - run + test in DAG order  (SELECT=... optional)"
	@echo "dbt-docs       - generate dbt docs"
	@echo "app            - run the Streamlit cockpit locally (reads the marts)"
	@echo "api            - run the copilot FastAPI service locally (needs GEMINI_API_KEY)"
	@echo "mcp            - run the MCP server (stdio) exposing the governed tools to MCP clients"
	@echo "copilot-test   - run the copilot + semantic unit tests (no LLM, no BigQuery)"
	@echo "mcp-test       - run the MCP server unit tests (.venv-mcp; no live client, no BigQuery)"
	@echo "airflow-start  - local Airflow via Astro CLI (Cosmos dbt DAG; needs Docker)"
	@echo "airflow-stop   - stop the local Airflow"
	@echo "docker-build   - build the Cloud Run image locally"
	@echo "tf-init        - terraform init (deploy layer)"
	@echo "tf-bootstrap   - create Artifact Registry + secret container + enable APIs"
	@echo "secret-push    - push GEMINI_API_KEY into Secret Manager (value stays out of git/tf)"
	@echo "image-push     - build (linux/amd64) + push the image to Artifact Registry"
	@echo "deploy         - terraform apply the Cloud Run service; prints the public URL"
	@echo "trim           - drop raw GCS object + raw BQ table, keep marts (zero-storage resting state)"
	@echo "teardown       - terraform destroy the serving layer (data layer kept)"

# Full pipeline: raw ingestion, then build + test the dbt DAG.
# NOTE: accept Kaggle competition rules before running this target (see .env.example).
hydrate:
	$(PYTHON) scripts/ingest.py
	$(DBT) build --project-dir $(DBT_DIR)

dbt-debug:
	$(DBT) debug --project-dir $(DBT_DIR)

dbt-run:
	$(DBT) run --project-dir $(DBT_DIR) $(if $(SELECT),-s $(SELECT),)

dbt-test:
	$(DBT) test --project-dir $(DBT_DIR) $(if $(SELECT),-s $(SELECT),)

dbt-build:
	$(DBT) build --project-dir $(DBT_DIR) $(if $(SELECT),-s $(SELECT),)

dbt-docs:
	$(DBT) docs generate --project-dir $(DBT_DIR)

# Local BI cockpit. Reads the marts via ADC; wrap queries in @st.cache_data.
app:
	$(APP_PYTHON) -m streamlit run app/main.py

# Local copilot API (FastAPI + Gemini + ADK). Governed tools over the semantic layer.
api:
	$(COPILOT_PYTHON) -m uvicorn copilot.api:app --reload --port 8000

# Copilot + semantic unit tests (no LLM, no BigQuery — the model is faked).
copilot-test:
	$(COPILOT_PYTHON) -m pytest tests/ -q --ignore=tests/test_mcp_server.py

# MCP server (stdio transport) — same governed tools as the copilot, for any MCP client.
mcp:
	$(MCP_PYTHON) -m copilot.mcp_server

# MCP server unit tests (its own 3.10+ venv; no live client, no BigQuery).
mcp-test:
	$(MCP_PYTHON) -m pytest tests/test_mcp_server.py -q

# Local Airflow (Astronomer) — Cosmos renders each dbt model as its own task.
# Needs Docker running + the Astro CLI (https://docs.astronomer.io/astro/cli/install-cli).
# The Airflow pipeline includes the monthly digest generation task (post-dbt-test).
airflow-start:
	cd airflow && astro dev start

airflow-stop:
	cd airflow && astro dev stop

# --- Deploy -----------------------------------------------------------------------
# Build the Cloud Run image locally (single container, isolated venvs).
docker-build:
	docker build -t card-acquisition-funnel:local .

tf-init:
	$(TF) init

# Create only the pieces needed before we can push: registry + secret + APIs.
# The Cloud Run service itself comes later in `deploy`, once the image exists.
tf-bootstrap:
	$(TF) apply $(TF_VARS) -var image=$(AR_IMAGE) \
		-target=google_project_service.apis \
		-target=google_artifact_registry_repository.funnel \
		-target=google_secret_manager_secret.gemini

# Push the Gemini key value into the secret Terraform created — value stays out of git/tf state.
secret-push:
	printf %s "$(GEMINI_API_KEY)" | gcloud secrets versions add gemini-api-key \
		--project=$(GCP_PROJECT) --data-file=-

# Build for Cloud Run's amd64 and push to Artifact Registry.
image-push:
	gcloud auth configure-docker $(GCP_REGION)-docker.pkg.dev --quiet
	docker build --platform linux/amd64 -t $(AR_IMAGE) .
	docker push $(AR_IMAGE)

# Create/patch the Cloud Run service and wire the image; print the public URL.
deploy:
	$(TF) apply $(TF_VARS) -var image=$(AR_IMAGE)
	@echo "Deployed at: $$($(TF) output -raw url)"

# Ephemeral raw: keep the marts (serving layer), drop the heavy raw layer.
# Re-hydrate anytime with `make hydrate`.
trim:
	@echo "Trimming raw layer (marts are kept)..."
	-gsutil -m rm -r gs://$(GCS_BUCKET)/santander/ 2>/dev/null || true
	-bq rm -f -t $(GCP_PROJECT):$(BQ_DATASET).$(BQ_RAW_TABLE)
	@echo "Done. Re-hydrate anytime with: make hydrate"

# Destroy the serving layer (Cloud Run, SA, IAM, registry, secret). The data layer
# (GCS raw bucket + BigQuery datasets) is left intact — use `make trim` to drop raw.
teardown:
	$(TF) destroy $(TF_VARS) -var image=$(AR_IMAGE)
