# ── API enablement ────────────────────────────────────────────────────────
resource "google_project_service" "services" {
  for_each = toset([
    "run.googleapis.com", "sqladmin.googleapis.com", "secretmanager.googleapis.com",
    "artifactregistry.googleapis.com", "bigquery.googleapis.com",
    "cloudscheduler.googleapis.com", "servicenetworking.googleapis.com",
    "compute.googleapis.com", "iam.googleapis.com",
  ])
  service            = each.value
  disable_on_destroy = false
}

# ── Artifact Registry ─────────────────────────────────────────────────────
resource "google_artifact_registry_repository" "docker" {
  location      = var.region
  repository_id = "tutor"
  format        = "DOCKER"
  depends_on    = [google_project_service.services]
}

# ── Red privada para Cloud SQL (solo Cloud Run la alcanza) ────────────────
resource "google_compute_global_address" "private_ip" {
  name          = "cloudsql-private-ip"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16
  network       = "default"
}

resource "google_service_networking_connection" "private_vpc" {
  service                 = "servicenetworking.googleapis.com"
  network                 = "default"
  reserved_peering_ranges = [google_compute_global_address.private_ip.name]
}

# ── Cloud SQL: instancia mínima, SOLO IP privada ──────────────────────────
resource "random_password" "db" {
  length  = 24
  special = false
}

resource "google_sql_database_instance" "postgres" {
  name             = "tutor-db"
  database_version = "POSTGRES_16"
  region           = var.region
  deletion_protection = false # mínimo/demo; subir a true en producción real

  settings {
    edition           = "ENTERPRISE"  # edición que soporta el tier mínimo
    tier              = "db-f1-micro" # instancia mínima
    availability_type = "ZONAL"
    disk_size         = 10
    disk_autoresize   = true

    ip_configuration {
      ipv4_enabled    = false           # sin IP pública
      private_network = "projects/cohort-fundador/global/networks/default"
    }

    database_flags {
      name  = "log_min_duration_statement"
      value = "500" # observabilidad: statements lentos al log de errores
    }
    database_flags {
      name  = "log_connections"
      value = "on"
    }
  }

  depends_on = [google_service_networking_connection.private_vpc]
}

resource "google_sql_database" "tutor" {
  name     = "tutor"
  instance = google_sql_database_instance.postgres.name
}

resource "google_sql_user" "tutor" {
  name     = "tutor"
  instance = google_sql_database_instance.postgres.name
  password = random_password.db.result
}

# ── Secret Manager ────────────────────────────────────────────────────────
resource "google_secret_manager_secret" "db_password" {
  secret_id = "tutor-db-password"
  replication {
    auto {}
  }
}
resource "google_secret_manager_secret_version" "db_password" {
  secret      = google_secret_manager_secret.db_password.id
  secret_data = random_password.db.result
}

resource "google_secret_manager_secret" "gemini_key" {
  secret_id = "tutor-gemini-api-key"
  replication {
    auto {}
  }
}
resource "google_secret_manager_secret_version" "gemini_key" {
  secret      = google_secret_manager_secret.gemini_key.id
  secret_data = var.gemini_api_key
}

resource "random_password" "jwt" {
  length  = 48
  special = false
}
resource "google_secret_manager_secret" "jwt_key" {
  secret_id = "tutor-jwt-signing-key"
  replication {
    auto {}
  }
}
resource "google_secret_manager_secret_version" "jwt_key" {
  secret      = google_secret_manager_secret.jwt_key.id
  secret_data = random_password.jwt.result
}

# ── Service Accounts (mínimo privilegio) ──────────────────────────────────
resource "google_service_account" "runtime" {
  account_id   = "tutor-runtime"
  display_name = "Tutor Cloud Run runtime"
}
resource "google_service_account" "etl" {
  account_id   = "tutor-etl"
  display_name = "Tutor ETL job"
}

resource "google_project_iam_member" "runtime" {
  for_each = toset([
    "roles/cloudsql.client",             # conectar a Cloud SQL por IP privada
    "roles/secretmanager.secretAccessor", # leer los 3 secretos
    "roles/logging.logWriter",
    "roles/artifactregistry.reader",
  ])
  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.runtime.email}"
}

resource "google_project_iam_member" "etl" {
  for_each = toset([
    "roles/cloudsql.client",
    "roles/secretmanager.secretAccessor", # db-password para el DSN
    "roles/bigquery.dataEditor",          # escribir en tutor_analytics
    "roles/bigquery.jobUser",             # crear load jobs de BQ
    "roles/logging.logWriter",
    "roles/artifactregistry.reader",
  ])
  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.etl.email}"
}

# ── BigQuery (analítica) ──────────────────────────────────────────────────
resource "google_bigquery_dataset" "analytics" {
  dataset_id    = "tutor_analytics"
  friendly_name = "Analítica del tutor"
  location      = "EU"
}

# ── Cloud Run (un solo contenedor: front+back) ────────────────────────────
resource "google_cloud_run_v2_service" "app" {
  name     = "tutor-app"
  location = var.region
  deletion_protection = false
  ingress  = "INGRESS_TRAFFIC_ALL" # front público; los datos quedan tras JWT (auditoría F-03)

  template {
    service_account                  = google_service_account.runtime.email
    max_instance_request_concurrency = 40
    scaling {
      min_instance_count = 0
      max_instance_count = 1
    }
    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [google_sql_database_instance.postgres.connection_name]
      }
    }
    vpc_access {
      egress = "PRIVATE_RANGES_ONLY"
      network_interfaces {
        network    = "default"
        subnetwork = "default"
      }
    }
    containers {
      image = "${google_artifact_registry_repository.docker.location}-docker.pkg.dev/${var.project_id}/tutor/app:latest"
      resources {
        limits = { cpu = "1", memory = "512Mi" }
      }
      volume_mounts {
        name       = "cloudsql"
        mount_path = "/cloudsql"
      }
      env {
        name  = "ENVIRONMENT"
        value = "cloud"
      }
      env {
        name  = "CLOUDSQL_INSTANCE"
        value = google_sql_database_instance.postgres.connection_name
      }
      env {
        name  = "POSTGRES_USER"
        value = google_sql_user.tutor.name
      }
      env {
        name  = "POSTGRES_DB"
        value = google_sql_database.tutor.name
      }
      env {
        name = "POSTGRES_PASSWORD"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.db_password.secret_id
            version = "latest"
          }
        }
      }
      env {
        name = "GEMINI_API_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.gemini_key.secret_id
            version = "latest"
          }
        }
      }
      env {
        name = "JWT_SECRET"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.jwt_key.secret_id
            version = "latest"
          }
        }
      }
    }
  }
  depends_on = [google_secret_manager_secret_version.gemini_key, google_secret_manager_secret_version.jwt_key]
}

# Acceso público SOLO a través de esta URL del servicio (front + /api/login|register)
data "google_iam_policy" "public_app" {
  binding {
    role    = "roles/run.invoker"
    members = ["allUsers"]
  }
}
resource "google_cloud_run_v2_service_iam_policy" "public_app" {
  name     = google_cloud_run_v2_service.app.name
  location = var.region
  policy_data = data.google_iam_policy.public_app.policy_data
}

# ── ETL: Cloud Run Job programado con Cloud Scheduler ────────────────────
resource "google_cloud_run_v2_job" "etl" {
  name     = "tutor-etl"
  location = var.region
  deletion_protection = false
  template {
    template {
      service_account = google_service_account.etl.email
      vpc_access {
        egress = "PRIVATE_RANGES_ONLY"
        network_interfaces {
          network    = "default"
          subnetwork = "default"
        }
      }
      volumes {
        name = "cloudsql"
        cloud_sql_instance {
          instances = [google_sql_database_instance.postgres.connection_name]
        }
      }
      containers {
        image = "${google_artifact_registry_repository.docker.location}-docker.pkg.dev/${var.project_id}/tutor/etl:latest"
        env {
          name  = "BIGQUERY_DATASET"
          value = google_bigquery_dataset.analytics.dataset_id
        }
        env {
          name  = "GCP_PROJECT"
          value = var.project_id
        }
        env {
          name  = "CLOUDSQL_INSTANCE"
          value = google_sql_database_instance.postgres.connection_name
        }
        env {
          name  = "POSTGRES_USER"
          value = google_sql_user.tutor.name
        }
        env {
          name  = "POSTGRES_DB"
          value = google_sql_database.tutor.name
        }
        env {
          name = "POSTGRES_PASSWORD"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.db_password.secret_id
              version = "latest"
            }
          }
        }
        volume_mounts {
          name       = "cloudsql"
          mount_path = "/cloudsql"
        }
      }
    }
  }
}

resource "google_cloud_scheduler_job" "etl_daily" {
  name             = "tutor-etl-daily"
  schedule         = "0 4 * * *" # diario 04:00 UTC
  attempt_deadline = "600s"

  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.project_id}/locations/${var.region}/jobs/${google_cloud_run_v2_job.etl.name}:run"
    oidc_token {
      service_account_email = google_service_account.etl.email
    }
  }
  depends_on = [google_project_service.services]
}

# ── Outputs ───────────────────────────────────────────────────────────────
output "cloud_run_url" {
  value = google_cloud_run_v2_service.app.uri
}
output "cloudsql_connection_name" {
  value = google_sql_database_instance.postgres.connection_name
}
output "artifact_registry" {
  value = "${google_artifact_registry_repository.docker.location}-docker.pkg.dev/${var.project_id}/tutor"
}
