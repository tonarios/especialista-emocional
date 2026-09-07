# ah-emociones — infraestructura GCP mínima (M9)
#
# Arquitectura elegida por el owner (ver docs/presupuesto-gcp.md, opción A):
#   - Cloud Run          : contenedor único back+front, ESCALA A CERO
#   - Firestore (Native) : auth, perfiles, sesiones ADK y auditoría
#   - Vertex AI          : gemini-2.5-flash-lite (LLM) + gemini-embedding-001
#   - BigQuery           : analítica de métricas y metadatos (NUNCA texto de chats)
#   - Artifact Registry  : imagen docker, con política de limpieza
#   - Secret Manager     : JWT_SECRET (único secreto; Vertex va por service account)
#   - GCS                : estado remoto de Terraform
#   - Billing budget     : alerta de gasto, la red de seguridad de todo lo anterior
#
# Deliberadamente NO hay: Cloud SQL, VPC Connector, pgvector, ni servicio de
# vectores. El índice FAISS (~15 MB con 3072 dims) va horneado en la imagen.
#
# Piso de costo con cero uso: ~USD 0.28/mes. Ver docs/presupuesto-gcp.md.
#
# NO aplicar sin visto bueno explícito del owner (política heredada del repo base).

terraform {
  required_version = ">= 1.6"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# ── APIs necesarias ────────────────────────────────────────────────────────
# Ya activas en el proyecto: aiplatform, bigquery, storage.
# `disable_on_destroy = false`: apagar una API al destruir puede romper otros
# recursos del proyecto que la compartan.
resource "google_project_service" "services" {
  for_each = toset([
    "run.googleapis.com",
    "firestore.googleapis.com",
    "aiplatform.googleapis.com",
    "bigquery.googleapis.com",
    "artifactregistry.googleapis.com",
    "secretmanager.googleapis.com",
    "storage.googleapis.com",
    "cloudbilling.googleapis.com",
    "billingbudgets.googleapis.com",
  ])
  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}
