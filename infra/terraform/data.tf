# Almacenamiento de datos: Firestore (operacional) + BigQuery (analítico).
#
# Decisión (docs/presupuesto-gcp.md §5, opción A): Firestore en vez de Cloud SQL.
# Cloud SQL no escala a cero — su instancia más barata cuesta ~USD 9.70/mes aunque
# nadie use el sistema. Firestore cabe entero en el free tier (50k lecturas/día,
# 20k escrituras/día, 1 GiB) para el volumen de este proyecto: ~USD 0/mes.

# ── Firestore (Native) — auth, perfiles, sesiones ADK, auditoría ───────────
resource "google_firestore_database" "main" {
  project     = var.project_id
  name        = "(default)"
  location_id = var.firestore_location
  type        = "FIRESTORE_NATIVE"

  # Point-in-time recovery cuesta extra y no aporta a un proyecto académico.
  point_in_time_recovery_enablement = "POINT_IN_TIME_RECOVERY_DISABLED"
  delete_protection_state           = "DELETE_PROTECTION_DISABLED"
  deletion_policy                   = "DELETE"

  depends_on = [google_project_service.services]
}

# Consultar el historial de un portador ordenado por fecha necesita índice
# compuesto: la colección se filtra por user_id y se ordena por ts.
resource "google_firestore_index" "consultations_by_user" {
  project    = var.project_id
  database   = google_firestore_database.main.name
  collection = "consultations"

  fields {
    field_path = "user_id"
    order      = "ASCENDING"
  }
  fields {
    field_path = "ts"
    order      = "DESCENDING"
  }
}

# Los eventos de una sesión ADK se leen en orden de llegada.
resource "google_firestore_index" "events_by_session" {
  project    = var.project_id
  database   = google_firestore_database.main.name
  collection = "session_events"

  fields {
    field_path = "session_key"
    order      = "ASCENDING"
  }
  fields {
    field_path = "ts"
    order      = "ASCENDING"
  }
}

# ── BigQuery — analítica ───────────────────────────────────────────────────
#
# REGLA DURA (NFR-07 + FR-05b): aquí van métricas y metadatos, NUNCA el texto de
# las conversaciones. Son datos de salud. El identificador es `user_hash` (hash
# con sal del email), que permite contar usuarios distintos y medir retención
# sin guardar identidad en el almacén analítico.

resource "google_bigquery_dataset" "analytics" {
  dataset_id    = "ah_emociones_analytics"
  friendly_name = "Analítica de ah-emociones (métricas y metadatos, sin texto de chats)"
  description   = "Sin PII ni contenido de conversaciones: NFR-07. El usuario se identifica por hash con sal."
  location      = var.bigquery_location

  depends_on = [google_project_service.services]
}

resource "google_bigquery_table" "consultas" {
  dataset_id          = google_bigquery_dataset.analytics.dataset_id
  table_id            = "consultas"
  description         = "Un registro por turno de chat. Términos y riesgo, nunca el mensaje."
  deletion_protection = false

  time_partitioning {
    type  = "DAY"
    field = "ts"
  }
  clustering = ["risk_tier", "kind"]

  schema = jsonencode([
    { name = "ts", type = "TIMESTAMP", mode = "REQUIRED", description = "Momento del turno" },
    { name = "user_hash", type = "STRING", mode = "REQUIRED", description = "Hash con sal del email — nunca el email" },
    { name = "session_id", type = "STRING", mode = "NULLABLE" },
    { name = "symptom_slug", type = "STRING", mode = "REPEATED", description = "Síntomas extraídos, normalizados" },
    { name = "term_slug", type = "STRING", mode = "REPEATED", description = "Términos citados tras la intersección (§9)" },
    { name = "risk_tier", type = "STRING", mode = "NULLABLE", description = "Nivel de riesgo que eligió la plantilla" },
    { name = "kind", type = "STRING", mode = "REQUIRED", description = "respuesta | sin_cobertura | emergency | blocked" },
    { name = "latency_ms", type = "INTEGER", mode = "NULLABLE" },
    { name = "input_tokens", type = "INTEGER", mode = "NULLABLE", description = "Para seguir el gasto de Vertex" },
    { name = "output_tokens", type = "INTEGER", mode = "NULLABLE" },
  ])
}

resource "google_bigquery_table" "recuperacion" {
  dataset_id          = google_bigquery_dataset.analytics.dataset_id
  table_id            = "recuperacion"
  description         = "Diagnóstico del RAG en producción: dónde falla la cobertura (deuda de sinonimia)."
  deletion_protection = false

  time_partitioning {
    type  = "DAY"
    field = "ts"
  }

  schema = jsonencode([
    { name = "ts", type = "TIMESTAMP", mode = "REQUIRED" },
    { name = "query_hash", type = "STRING", mode = "REQUIRED", description = "Hash de la consulta — nunca el texto" },
    { name = "k", type = "INTEGER", mode = "REQUIRED" },
    { name = "hit_lexico", type = "BOOLEAN", mode = "REQUIRED", description = "Hubo match nominal de título/alias (el umbral τ, FR-09b)" },
    { name = "sin_cobertura", type = "BOOLEAN", mode = "REQUIRED" },
    { name = "top_slugs", type = "STRING", mode = "REPEATED" },
    { name = "top_score", type = "FLOAT", mode = "NULLABLE" },
  ])
}

resource "google_bigquery_table" "guardarrailes" {
  dataset_id          = google_bigquery_dataset.analytics.dataset_id
  table_id            = "guardarrailes"
  description         = "Cada vez que dispara un guardarraíl determinista. Es la evidencia viva de FR-06 y NFR-01."
  deletion_protection = false

  time_partitioning {
    type  = "DAY"
    field = "ts"
  }

  schema = jsonencode([
    { name = "ts", type = "TIMESTAMP", mode = "REQUIRED" },
    { name = "tipo", type = "STRING", mode = "REQUIRED", description = "emergencia | injection | prescripcion | diagnostico_forzado" },
    { name = "grupo", type = "STRING", mode = "NULLABLE", description = "Grupo de rag/emergency_patterns.json, si aplica" },
    { name = "user_hash", type = "STRING", mode = "NULLABLE" },
  ])
}

resource "google_bigquery_table" "eval" {
  dataset_id          = google_bigquery_dataset.analytics.dataset_id
  table_id            = "eval"
  description         = "Serie histórica de scripts/evidence.sh: permite ver si el recall se degrada entre corridas, no solo la foto de la última."
  deletion_protection = false

  schema = jsonencode([
    { name = "run_id", type = "STRING", mode = "REQUIRED" },
    { name = "ts", type = "TIMESTAMP", mode = "REQUIRED" },
    { name = "git_sha", type = "STRING", mode = "NULLABLE" },
    { name = "tipo", type = "STRING", mode = "REQUIRED", description = "overall | single | alias | multi" },
    { name = "n", type = "INTEGER", mode = "REQUIRED" },
    { name = "recall", type = "FLOAT", mode = "REQUIRED" },
    { name = "ci95_low", type = "FLOAT", mode = "NULLABLE" },
    { name = "ci95_high", type = "FLOAT", mode = "NULLABLE" },
    { name = "latency_mean_s", type = "FLOAT", mode = "NULLABLE" },
    { name = "llm_model", type = "STRING", mode = "NULLABLE", description = "Distingue corridas con gemma4 local de las de Vertex" },
  ])
}
