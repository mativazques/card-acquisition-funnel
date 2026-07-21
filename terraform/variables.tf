variable "project_id" {
  type        = string
  description = "GCP project for the serving layer (card-acquisition-funnel-2026)."
}

variable "region" {
  type        = string
  default     = "us-central1"
  description = "Region for Artifact Registry + both Cloud Run services."
}

variable "bq_marts_dataset" {
  type        = string
  default     = "analytics_marts"
  description = "Existing BigQuery marts dataset the runtime SA gets READ-ONLY access to. NOT created here — the data layer is bootstrapped by hand so Terraform can never destroy loaded data."
}

variable "image_api" {
  type        = string
  description = "Full Artifact Registry image ref for the copilot API (…/funnel/copilot-api:latest)."
}

variable "image_app" {
  type        = string
  description = "Full Artifact Registry image ref for the Streamlit cockpit (…/funnel/cockpit:latest)."
}
