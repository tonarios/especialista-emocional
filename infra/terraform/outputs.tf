output "cloud_run_url" {
  description = "URL pública del frontend."
  value       = google_cloud_run_v2_service.app.uri
}

output "artifact_registry" {
  description = "Destino del docker push."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.docker.repository_id}"
}

output "runtime_service_account" {
  description = "Identidad del contenedor (sin claves descargables)."
  value       = google_service_account.runtime.email
}

output "bigquery_dataset" {
  description = "Dataset de analítica. Solo métricas y metadatos (NFR-07)."
  value       = "${var.project_id}.${google_bigquery_dataset.analytics.dataset_id}"
}

output "firestore_database" {
  value = google_firestore_database.main.name
}

output "tfstate_bucket" {
  value = google_storage_bucket.tfstate.name
}
