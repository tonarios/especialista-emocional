# Cloud Run — contenedor único (back + front), escala a cero.
#
# `min_instance_count = 0` es la restricción que fijó el owner: sin tráfico no
# se paga compute. El precio de eso es el arranque en frío; por eso la imagen se
# adelgazó a 147 MB comprimidos (docs/migration.md) y se activa startup_cpu_boost.

resource "google_cloud_run_v2_service" "app" {
  # Ojo: Cloud Run reserva los prefijos "ah-" y "aef-" (ver variables.tf).
  name     = var.run_service_name
  location = var.region

  deletion_protection = false

  # El frontend es público; TODO endpoint de datos exige Bearer JWT (FR-17).
  ingress = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.runtime.email

    # Una instancia atiende varias peticiones a la vez: menos arranques en frío
    # y menos vCPU-s facturados.
    max_instance_request_concurrency = 20
    timeout                          = "120s"

    scaling {
      min_instance_count = 0 # ESCALA A CERO (restricción del owner)
      max_instance_count = var.max_instances
    }

    containers {
      image = var.image

      resources {
        limits = {
          cpu    = var.cpu
          memory = var.memory
        }
        # CPU solo mientras hay petición: es lo que hace que escalar a cero
        # signifique pagar cero.
        cpu_idle          = true
        startup_cpu_boost = true
      }

      ports {
        container_port = 8000
      }

      # ── Vertex AI ──────────────────────────────────────────────────────
      env {
        name  = "GOOGLE_GENAI_USE_VERTEXAI"
        value = "True"
      }
      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }
      env {
        name  = "GOOGLE_CLOUD_LOCATION"
        value = var.region
      }
      env {
        name  = "LLM_PROVIDER"
        value = "vertex"
      }
      env {
        name  = "LLM_MODEL"
        value = var.llm_model
      }
      env {
        name  = "EMBED_MODEL"
        value = var.embed_model
      }
      env {
        name  = "EMBED_DIMS"
        value = tostring(var.embed_dims)
      }

      # ── Persistencia ───────────────────────────────────────────────────
      env {
        name  = "STORAGE_BACKEND"
        value = "firestore"
      }
      env {
        name  = "FIRESTORE_DATABASE"
        value = google_firestore_database.main.name
      }
      env {
        name  = "BQ_DATASET"
        value = google_bigquery_dataset.analytics.dataset_id
      }

      # ── Secretos: se montan como referencia, nunca como valor ──────────
      env {
        name = "JWT_SECRET"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.jwt.secret_id
            version = "latest"
          }
        }
      }
      env {
        name = "ANALYTICS_SALT"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.analytics_salt.secret_id
            version = "latest"
          }
        }
      }

      startup_probe {
        http_get {
          path = "/health"
        }
        initial_delay_seconds = 10
        period_seconds        = 5
        failure_threshold     = 30 # imagen grande: se le da margen al primer arranque
      }
    }
  }

  depends_on = [
    google_project_service.services,
    google_secret_manager_secret_version.jwt,
    google_secret_manager_secret_iam_member.runtime_jwt,
  ]
}

# El frontend tiene que ser alcanzable sin credencial de GCP; la protección de
# los datos es el JWT de la app (FR-17), no el IAM de Cloud Run.
resource "google_cloud_run_v2_service_iam_member" "public" {
  project  = var.project_id
  location = google_cloud_run_v2_service.app.location
  name     = google_cloud_run_v2_service.app.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
