output "cockpit_url" {
  description = "Public URL of the Streamlit cockpit (the demo link)."
  value       = google_cloud_run_v2_service.app.uri
}

output "api_url" {
  description = "Public URL of the copilot API (the cockpit's /ask backend)."
  value       = google_cloud_run_v2_service.api.uri
}

output "runtime_service_account" {
  description = "The least-privilege runtime SA (read-only marts + jobUser + secret accessor)."
  value       = google_service_account.runtime.email
}
