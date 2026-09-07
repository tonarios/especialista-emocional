# Identidad y permisos — mínimo privilegio.
#
# El principio aquí: NINGÚN rol a nivel proyecto que pueda acotarse al recurso.
# Secret Manager y BigQuery se conceden sobre el secreto y el dataset concretos,
# no sobre el proyecto entero.
#
# Nótese que NO hay clave de API de Vertex: la autenticación es por service
# account (roles/aiplatform.user). Un secreto menos que rotar y que filtrar.

resource "google_service_account" "runtime" {
  account_id   = "${var.service_name}-run"
  display_name = "Runtime de Cloud Run de ah-emociones"
  description  = "Identidad del contenedor. Sin claves descargables."
}

# ── Roles a nivel proyecto: solo los que NO admiten alcance por recurso ────
resource "google_project_iam_member" "runtime" {
  for_each = toset([
    "roles/aiplatform.user",   # invocar Gemini y embeddings en Vertex
    "roles/datastore.user",    # leer/escribir Firestore (NO datastore.owner)
    "roles/bigquery.jobUser",  # lanzar los inserts; los datos van por IAM de dataset
    "roles/logging.logWriter", # escribir logs (sin contenido de chats, NFR-07)
  ])
  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.runtime.email}"
}

# ── Alcance por recurso ───────────────────────────────────────────────────

# Solo este secreto, no todos los del proyecto.
resource "google_secret_manager_secret_iam_member" "runtime_jwt" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.jwt.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.runtime.email}"
}

# Solo este dataset, y como editor de datos (no admin: no puede borrarlo).
resource "google_bigquery_dataset_iam_member" "runtime_analytics" {
  dataset_id = google_bigquery_dataset.analytics.dataset_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${google_service_account.runtime.email}"
}

# Solo este repositorio de imágenes, en lectura.
resource "google_artifact_registry_repository_iam_member" "runtime_pull" {
  project    = var.project_id
  location   = google_artifact_registry_repository.docker.location
  repository = google_artifact_registry_repository.docker.name
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${google_service_account.runtime.email}"
}
