# Serving layer ONLY. Deliberately contains NO google_bigquery_dataset and NO
# google_storage_bucket resource — the data layer (raw GCS + BigQuery datasets/marts) is
# bootstrapped by hand, so `terraform destroy` here can never drop loaded data. The only
# data-plane touch is a single scoped, non-authoritative READ-ONLY IAM member on the
# existing marts dataset; destroying it revokes access, it does not delete the dataset.

locals {
  services = [
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
    "secretmanager.googleapis.com",
    "iam.googleapis.com",
    "cloudresourcemanager.googleapis.com",
  ]
}

resource "google_project_service" "apis" {
  for_each = toset(local.services)
  service  = each.value

  # Keep the APIs enabled if the serving layer is torn down — other tooling may rely on them.
  disable_on_destroy = false
}

# --- Artifact Registry: one docker repo, keep only the `latest` tag of each image ----------
resource "google_artifact_registry_repository" "funnel" {
  location      = var.region
  repository_id = "funnel"
  format        = "DOCKER"
  description   = "Cloud Run images for card-acquisition-funnel (cockpit + copilot-api)."

  # Each push overwrites the `latest` tag, orphaning the previous digest. Keep tagged
  # `latest`, delete anything untagged → storage stays under the 0.5 GB free tier.
  cleanup_policy_dry_run = false

  cleanup_policies {
    id     = "keep-latest-tagged"
    action = "KEEP"
    condition {
      tag_state    = "TAGGED"
      tag_prefixes = ["latest"]
    }
  }

  cleanup_policies {
    id     = "delete-untagged"
    action = "DELETE"
    condition {
      tag_state  = "UNTAGGED"
      older_than = "0s"
    }
  }

  depends_on = [google_project_service.apis]
}

# --- Runtime service account (least privilege, shared by both services) --------------------
resource "google_service_account" "runtime" {
  account_id   = "funnel-run"
  display_name = "card-acquisition-funnel Cloud Run runtime (read-only marts)"
  depends_on   = [google_project_service.apis]
}

# READ-ONLY on the existing marts dataset only. Non-authoritative member binding: it adds
# our SA and leaves any other dataset ACLs untouched. Destroying it revokes access, never
# the data. The dataset itself is NOT a Terraform resource.
resource "google_bigquery_dataset_iam_member" "marts_viewer" {
  dataset_id = var.bq_marts_dataset
  role       = "roles/bigquery.dataViewer"
  member     = "serviceAccount:${google_service_account.runtime.email}"
}

# jobUser is project-scoped (BigQuery has no dataset-level job permission) — lets the SA run
# read queries. No write/create/delete data roles anywhere.
resource "google_project_iam_member" "job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.runtime.email}"
}

# --- Secret: the Gemini AI Studio key (value pushed out-of-band via `make secret-push`) ----
resource "google_secret_manager_secret" "gemini" {
  secret_id = "gemini-api-key"
  replication {
    auto {}
  }
  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_iam_member" "gemini_accessor" {
  secret_id = google_secret_manager_secret.gemini.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.runtime.email}"
}

# --- Copilot API service (protobuf-6 / py3.12 image) --------------------------------------
resource "google_cloud_run_v2_service" "api" {
  name                = "funnel-copilot-api"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false

  template {
    service_account = google_service_account.runtime.email

    scaling {
      min_instance_count = 0 # scale-to-zero → $0 idle
      max_instance_count = 2 # cap the blast radius of the free-tier quota
    }

    max_instance_request_concurrency = 80

    containers {
      image = var.image_api

      ports {
        container_port = 8080
      }

      resources {
        cpu_idle = true # CPU allocated only while a request is in flight
        limits = {
          cpu    = "1"
          memory = "1Gi"
        }
      }

      env {
        name  = "GCP_PROJECT"
        value = var.project_id
      }
      env {
        name  = "BQ_DBT_DATASET"
        value = replace(var.bq_marts_dataset, "_marts", "")
      }
      # Stay on AI Studio free tier — Vertex bills. Explicitly pinned off (D19).
      env {
        name  = "GOOGLE_GENAI_USE_VERTEXAI"
        value = "false"
      }
      env {
        name = "GEMINI_API_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.gemini.secret_id
            version = "latest"
          }
        }
      }
    }
  }

  depends_on = [
    google_secret_manager_secret_iam_member.gemini_accessor,
    google_project_iam_member.job_user,
  ]
}

# --- Streamlit cockpit service (protobuf<6 / py3.9 image) — the public demo ----------------
resource "google_cloud_run_v2_service" "app" {
  name                = "funnel-cockpit"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false

  template {
    service_account = google_service_account.runtime.email

    scaling {
      min_instance_count = 0
      max_instance_count = 2
    }

    max_instance_request_concurrency = 80

    containers {
      image = var.image_app

      ports {
        container_port = 8080
      }

      resources {
        cpu_idle = true
        limits = {
          cpu    = "1"
          memory = "1Gi"
        }
      }

      env {
        name  = "GCP_PROJECT"
        value = var.project_id
      }
      env {
        name  = "BQ_DBT_DATASET"
        value = replace(var.bq_marts_dataset, "_marts", "")
      }
      # The cockpit's "Ask the copilot" tab calls the API by its public URL.
      env {
        name  = "COPILOT_API_URL"
        value = google_cloud_run_v2_service.api.uri
      }
    }
  }

  depends_on = [google_project_iam_member.job_user]
}

# --- Public access: both services are public; the API is guarded by its own L1–L4 hardening -
resource "google_cloud_run_v2_service_iam_member" "api_public" {
  location = google_cloud_run_v2_service.api.location
  name     = google_cloud_run_v2_service.api.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_cloud_run_v2_service_iam_member" "app_public" {
  location = google_cloud_run_v2_service.app.location
  name     = google_cloud_run_v2_service.app.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
