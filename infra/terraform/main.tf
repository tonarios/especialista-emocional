# Infraestructura GCP del tutor — proyecto cohort-fundador
#
# Componentes:
#   - Artifact Registry      : imágenes docker (app single-container + ETL)
#   - Cloud SQL PostgreSQL   : instancia MÍNIMA, SOLO IP privada (sin IP pública,
#                              sin authorized networks) -> solo alcanzable por
#                              Cloud Run vía la conexión de servicios privados.
#   - Secret Manager         : gemini-api-key, db-password, jwt-signing-key.
#   - Cloud Run              : un solo servicio (front+back) con los secretos
#                              montados como env var (nunca en la imagen).
#   - BigQuery               : dataset de analítica alimentado por el job ETL.
#
# NO aplicar hasta tener el visto bueno. Ver infra/terraform/README.md.

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

variable "project_id" {
  type    = string
  default = "cohort-fundador"
}

variable "region" {
  type    = string
  default = "europe-west1"
}

variable "gemini_api_key" {
  type      = string
  sensitive = true # pasar con TF_VAR_gemini_api_key (nunca en código)
}
