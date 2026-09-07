# Variables. Nada sensible lleva `default`: se pasan por TF_VAR_* o -var-file
# con un .tfvars que NUNCA se commitea (está en .gitignore).

variable "project_id" {
  type        = string
  description = "Proyecto GCP destino."
  default     = "diplomado-499206"
}

variable "region" {
  type        = string
  description = "Región de Cloud Run y Vertex. us-central1 es tier 1 (la tarifa más baja de Cloud Run) y tiene disponibles los modelos Gemini usados."
  default     = "us-central1"
}

variable "firestore_location" {
  type        = string
  description = "Ubicación de Firestore. Región simple (no multi-región): más barata y suficiente para un proyecto académico."
  default     = "us-central1"
}

variable "bigquery_location" {
  type        = string
  description = "Ubicación del dataset de analítica."
  default     = "US"
}

variable "service_name" {
  type        = string
  description = "Prefijo de recursos (registry, service account, secretos)."
  default     = "ah-emociones"
}

variable "run_service_name" {
  type        = string
  description = <<-EOT
    Nombre del servicio de Cloud Run. Va aparte de `service_name` porque
    Cloud Run RESERVA los prefijos 'ah-' y 'aef-' para uso interno y rechaza
    la creación con un 400. Los demás recursos sí admiten el prefijo del
    proyecto, así que solo este cambia.
  EOT
  default     = "emociones-app"

  validation {
    condition     = !startswith(var.run_service_name, "ah-") && !startswith(var.run_service_name, "aef-")
    error_message = "Cloud Run rechaza los nombres que empiezan por 'ah-' o 'aef-' (prefijos reservados)."
  }
}

variable "image" {
  type        = string
  description = <<-EOT
    Imagen a desplegar. Debe existir en Artifact Registry ANTES del apply:
      gcloud auth configure-docker us-central1-docker.pkg.dev
      docker build --platform linux/amd64 -t <esta ruta> .
      docker push <esta ruta>
    En `plan` no se valida que exista.
  EOT
  default     = null
}

# ── Modelos Vertex (los más baratos, ver docs/presupuesto-gcp.md §8) ────────

variable "llm_model" {
  type        = string
  description = "gemini-2.5-flash-lite: $0.10/1M in, $0.40/1M out — el más barato de la familia."
  default     = "gemini-2.5-flash-lite"
}

variable "embed_model" {
  type        = string
  description = "gemini-embedding-001: $0.15/1M tokens."
  default     = "gemini-embedding-001"
}

variable "embed_dims" {
  type        = number
  description = "Dimensiones del embedding. 3072 = sin truncar (decisión del owner). El índice FAISS ocupa ~15 MB dentro de la imagen."
  default     = 3072
}

# ── Cloud Run ──────────────────────────────────────────────────────────────

variable "cpu" {
  type    = string
  default = "1"
}

variable "memory" {
  type        = string
  description = "El índice FAISS (~15 MB) + BM25 + meta se cargan en memoria al arrancar."
  default     = "2Gi"
}

variable "max_instances" {
  type        = number
  description = "Tope de escalado: evita que una ráfaga se coma el free tier. 3 sobra para una demo."
  default     = 3
}

# ── Presupuesto ────────────────────────────────────────────────────────────

variable "billing_account" {
  type        = string
  description = "ID de la cuenta de facturación, para el budget de alertas. Vacío = no se crea el budget (requiere roles/billing.costsManager)."
  default     = ""
}

variable "budget_amount_usd" {
  type        = number
  description = "Tope mensual con alertas al 50/90/100%. El gasto previsto es ~$0.54/mes."
  default     = 5
}

variable "state_bucket" {
  type        = string
  description = "Bucket de GCS para el estado remoto de Terraform."
  default     = "ah-emociones-tfstate"
}
