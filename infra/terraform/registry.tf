# Artifact Registry + Secret Manager.
#
# Artifact Registry es, junto con Secret Manager, el ÚNICO gasto fijo del
# proyecto (~USD 0.28/mes en total). La política de limpieza existe para que no
# crezca: sin ella, cada push acumula 2,7 GB a $0.10/GB/mes.

resource "google_artifact_registry_repository" "docker" {
  location      = var.region
  repository_id = var.service_name
  description   = "Imagen única back+front de ah-emociones"
  format        = "DOCKER"

  # Conservar solo las 3 últimas versiones: el resto se borra solo.
  cleanup_policies {
    id     = "conservar-3-recientes"
    action = "KEEP"
    most_recent_versions {
      keep_count = 3
    }
  }
  cleanup_policies {
    id     = "borrar-lo-demas"
    action = "DELETE"
    condition {
      older_than = "2592000s" # 30 días
    }
  }

  depends_on = [google_project_service.services]
}

# ── Secret Manager: un solo secreto ───────────────────────────────────────
#
# JWT_SECRET es el único secreto real del sistema. Vertex se autentica por
# service account, así que no hay clave de API que guardar (a diferencia del
# repo base, que tenía gemini-api-key).
#
# El valor lo genera Terraform: nunca pasa por el repo ni por el shell.

resource "random_password" "jwt" {
  length  = 64
  special = false
}

resource "google_secret_manager_secret" "jwt" {
  secret_id = "${var.service_name}-jwt-secret"

  replication {
    auto {}
  }

  depends_on = [google_project_service.services]
}

resource "google_secret_manager_secret_version" "jwt" {
  secret      = google_secret_manager_secret.jwt.id
  secret_data = random_password.jwt.result
}

# Sal para el hash de usuario que va a BigQuery. Se guarda como secreto para que
# el `user_hash` del almacén analítico no sea reversible a email por fuerza bruta
# sobre el espacio de direcciones.
resource "random_password" "analytics_salt" {
  length  = 32
  special = false
}

resource "google_secret_manager_secret" "analytics_salt" {
  secret_id = "${var.service_name}-analytics-salt"

  replication {
    auto {}
  }

  depends_on = [google_project_service.services]
}

resource "google_secret_manager_secret_version" "analytics_salt" {
  secret      = google_secret_manager_secret.analytics_salt.id
  secret_data = random_password.analytics_salt.result
}

resource "google_secret_manager_secret_iam_member" "runtime_salt" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.analytics_salt.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.runtime.email}"
}
