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
# Two venvs, forced apart by a protobuf pin clash (streamlit<6 vs google-adk 6.x):
#   .venv        (Python 3.9)  — dbt + Streamlit + the semantic package.
#     python3 -m venv .venv && .venv/bin/pip install -r dbt/requirements.txt -r app/requirements.txt
#   .venv-agents (Python 3.12) — the agent layer: copilot API, digest job, MCP server.
#     python3.12 -m venv .venv-agents && .venv-agents/bin/pip install -r agents/requirements.txt
APP_PYTHON ?= .venv/bin/python
AGENTS_PYTHON ?= .venv-agents/bin/python
# dbt reads GCP_PROJECT / BQ_DBT_DATASET / BQ_LOCATION from the exported .env above.
export DBT_PROFILES_DIR := $(abspath dbt)

# Deploy: Terraform owns the SERVING layer only. Two scale-to-zero Cloud Run services,
# two images in Artifact Registry — Streamlit (protobuf<6) and the agent API (protobuf 6.x)
# cannot share one image, so they cannot share one container.
TF_DIR := terraform
GCP_REGION ?= us-central1
BQ_MARTS_DATASET ?= analytics_marts
AR_REPO := $(GCP_REGION)-docker.pkg.dev/$(GCP_PROJECT)/funnel
AR_IMAGE_API := $(AR_REPO)/copilot-api:latest
AR_IMAGE_APP := $(AR_REPO)/cockpit:latest
TF := terraform -chdir=$(TF_DIR)
TF_VARS := -var project_id=$(GCP_PROJECT) -var region=$(GCP_REGION) \
	-var bq_marts_dataset=$(BQ_MARTS_DATASET) \
	-var image_api=$(AR_IMAGE_API) -var image_app=$(AR_IMAGE_APP)

.DEFAULT_GOAL := help
.PHONY: help hydrate app api mcp agents-test semantic-test docker-build-api docker-build-app tf-init tf-bootstrap secret-push image-push deploy trim teardown dbt-debug dbt-run dbt-test dbt-build dbt-docs airflow-start airflow-stop

help:
	@echo "hydrate         - ingest Kaggle competition -> GCS -> BQ, then build + test dbt models"
	@echo "dbt-debug       - check dbt connects to BigQuery"
	@echo "dbt-run         - build dbt models        (SELECT=name to target one)"
	@echo "dbt-test        - run dbt data tests       (SELECT=... optional)"
	@echo "dbt-build       - run + test in DAG order  (SELECT=... optional)"
	@echo "dbt-docs        - generate dbt docs"
	@echo "app             - run the Streamlit cockpit locally (.venv; reads the marts)"
	@echo "api             - run the copilot FastAPI service locally (.venv-agents; needs GEMINI_API_KEY)"
	@echo "mcp             - run the MCP server (stdio) exposing the governed tools to MCP clients"
	@echo "agents-test     - run the agent-layer + semantic + MCP unit tests (.venv-agents; no LLM/BQ)"
	@echo "semantic-test   - run the semantic-layer contract tests in the BI venv (.venv; no LLM/BQ)"
	@echo "airflow-start   - local Airflow via Astro CLI (Cosmos dbt DAG; needs Docker)"
	@echo "airflow-stop    - stop the local Airflow"
	@echo "docker-build-api- build the copilot-API Cloud Run image locally"
	@echo "docker-build-app- build the Streamlit-cockpit Cloud Run image locally"
	@echo "tf-init         - terraform init (serving layer)"
	@echo "tf-bootstrap    - create Artifact Registry + secret container + enable APIs"
	@echo "secret-push     - push GEMINI_API_KEY into Secret Manager (value stays out of git/tf)"
	@echo "image-push      - build (linux/amd64) + push BOTH images to Artifact Registry"
	@echo "deploy          - terraform apply the two Cloud Run services; prints the public URLs"
	@echo "trim            - drop raw GCS object + raw BQ table, keep marts (zero-storage resting state)"
	@echo "teardown        - terraform destroy the serving layer (data layer kept)"

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

# Local BI cockpit (.venv, Python 3.9). Reads the marts via ADC; wrap queries in @st.cache_data.
app:
	$(APP_PYTHON) -m streamlit run app/main.py

# Local copilot API (FastAPI + Gemini + ADK) in .venv-agents. Governed tools over the semantic layer.
api:
	$(AGENTS_PYTHON) -m uvicorn agents.api:app --reload --port 8000

# Agent-layer + semantic + MCP unit tests, all in .venv-agents (no LLM, no BigQuery — the model is faked).
agents-test:
	PYTHONPATH=. $(AGENTS_PYTHON) -m pytest tests/ -q

# Semantic-layer contract tests in the BI venv, proving the package imports under Python 3.9 too.
semantic-test:
	PYTHONPATH=. $(APP_PYTHON) -m pytest tests/test_semantic.py -q

# MCP server (stdio transport) — same governed tools as the copilot, for any MCP client.
mcp:
	$(AGENTS_PYTHON) -m agents.mcp_server

# Local Airflow (Astronomer) — Cosmos renders each dbt model as its own task.
# Needs Docker running + the Astro CLI (https://docs.astronomer.io/astro/cli/install-cli).
# The Airflow pipeline includes the monthly digest generation task (post-dbt-test).
airflow-start:
	cd airflow && astro dev start

airflow-stop:
	cd airflow && astro dev stop

# --- Deploy -----------------------------------------------------------------------
# Build the two Cloud Run images locally (amd64 to match Cloud Run).
docker-build-api:
	docker build --platform linux/amd64 -f Dockerfile.api -t $(AR_IMAGE_API) .

docker-build-app:
	docker build --platform linux/amd64 -f Dockerfile.app -t $(AR_IMAGE_APP) .

tf-init:
	$(TF) init

# Create only the pieces needed before we can push: registry + secret + APIs.
# The Cloud Run services themselves come later in `deploy`, once the images exist.
tf-bootstrap:
	$(TF) apply $(TF_VARS) \
		-target=google_project_service.apis \
		-target=google_artifact_registry_repository.funnel \
		-target=google_secret_manager_secret.gemini

# Push the Gemini key value into the secret Terraform created — value stays out of git/tf state.
secret-push:
	printf %s "$(GEMINI_API_KEY)" | gcloud secrets versions add gemini-api-key \
		--project=$(GCP_PROJECT) --data-file=-

# Build for Cloud Run's amd64 and push BOTH images to Artifact Registry.
image-push: docker-build-api docker-build-app
	gcloud auth configure-docker $(GCP_REGION)-docker.pkg.dev --quiet
	docker push $(AR_IMAGE_API)
	docker push $(AR_IMAGE_APP)

# Create/patch the two Cloud Run services and wire the images; print the public URLs.
deploy:
	$(TF) apply $(TF_VARS)
	@echo "Cockpit (public demo): $$($(TF) output -raw cockpit_url)"
	@echo "Copilot API:           $$($(TF) output -raw api_url)"

# Ephemeral raw: keep the marts (serving layer), drop the heavy raw layer.
# Re-hydrate anytime with `make hydrate`.
trim:
	@echo "Trimming raw layer (marts are kept)..."
	-gsutil -m rm -r gs://$(GCS_BUCKET)/santander/ 2>/dev/null || true
	-bq rm -f -t $(GCP_PROJECT):$(BQ_DATASET).$(BQ_RAW_TABLE)
	@echo "Done. Re-hydrate anytime with: make hydrate"

# Destroy the serving layer (both Cloud Run services, SA, IAM, registry, secret). The data
# layer (GCS raw bucket + BigQuery datasets) is left intact — use `make trim` to drop raw.
teardown:
	$(TF) destroy $(TF_VARS)
