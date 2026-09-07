# Estado remoto de Terraform en GCS.
#
# Problema del huevo y la gallina: el backend necesita que el bucket exista
# ANTES de `terraform init`. Por eso el bucket se declara aquí como recurso y el
# backend se activa en un segundo paso (ver infra/terraform/README.md).
#
# El estado contiene valores en claro (el JWT_SECRET generado, entre otros), así
# que el bucket es privado, con versionado y acceso uniforme.

resource "google_storage_bucket" "tfstate" {
  name     = var.state_bucket
  location = var.bigquery_location
  project  = var.project_id

  # El estado lleva secretos en claro: nada de ACLs por objeto ni acceso público.
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  versioning {
    enabled = true
  }

  # Conservar histórico acotado: permite recuperar un estado corrupto sin que el
  # bucket crezca indefinidamente.
  lifecycle_rule {
    condition {
      num_newer_versions = 10
    }
    action {
      type = "Delete"
    }
  }

  depends_on = [google_project_service.services]
}
