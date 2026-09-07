# infra/terraform — ah-emociones

Infraestructura mínima en GCP. Ver [`../../docs/migration.md`](../../docs/migration.md) para
la arquitectura y [`../../docs/presupuesto-gcp.md`](../../docs/presupuesto-gcp.md) para costos.

**No aplicar sin visto bueno explícito del owner.**

## Comprobar (no crea nada)

```bash
scripts/infra_audit.sh
```

Encadena `fmt -check` → `validate` → `plan` contra el proyecto real → 17 aserciones de
seguridad sobre el plan → auditoría de secretos. Deja la evidencia en `outputs/evidence/`.

## Estado remoto

Huevo y gallina: el backend de GCS necesita que el bucket exista antes de `init`. Por eso el
bucket se declara como recurso (`state.tf`) y el backend se activa en un segundo paso:

```bash
terraform apply -target=google_storage_bucket.tfstate
```

y luego añadir a `main.tf`:

```hcl
terraform {
  backend "gcs" {
    bucket = "ah-emociones-tfstate"
    prefix = "ah-emociones"
  }
}
```

seguido de `terraform init -migrate-state`.

## Variables

Todas tienen default salvo `image` y `billing_account`. Nada sensible se commitea: los
`*.tfvars` están en `.gitignore` y los secretos los genera `random_password` para guardarlos
en Secret Manager, así que nunca pasan por el repo ni por el shell.

`.terraform.lock.hcl` **sí** se commitea: fija los hashes de los providers.
