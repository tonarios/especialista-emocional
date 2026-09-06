---
name: gcp-terraform
description: IaC con Terraform para GCP con recursos mínimos: Cloud Run (escala a 0) con contenedor único, Cloud SQL for PostgreSQL stock privado/auth-proxy, Secret Manager, Artifact Registry, GCS opcional e IAM mínimo. Gate = plan/validate válido; apply SOLO con visto bueno. M9 — acotado.
---

# gcp-terraform — M9: migración a GCP como IaC (acotado)

## Cuándo activar

- Al final (no bloquea nada anterior). Según §12 y §17.9: **`terraform plan` validado es suficiente** si el diplomado no exige despliegue vivo; `apply` solo con visto bueno explícito del owner.

## Entradas

- `infra/terraform/` del repo base (punto de partida).
- PRD §12 completo y NFR-10 (conexión privada y autenticada).

## Pasos

1. Adaptar Terraform:
   - **Cloud Run**: 1 servicio CPU, **escala a 0**, contenedor único back+front con índice FAISS en memoria (baked en imagen ~5 MB, o desde GCS — default propuesto: baked).
   - **Cloud SQL for PostgreSQL** stock (**SIN pgvector**) — IP privada, o la alternativa preferente por costo: **Cloud SQL Auth Proxy + IAM** (elimina el VPC Connector, §12).
   - **Secret Manager**: `JWT_SECRET`, credenciales DB; **Artifact Registry**: imagen; **GCS** (opcional): índice.
   - **Serverless VPC Connector**: solo si se elige IP privada de VPC (documentar por qué).
2. **IAM mínimo privilegio**: Cloud Run lee solo los secretos que necesita y accede a la BD.
3. Estado remoto en GCS; `*.tfvars` y secretos **fuera del repo** (gestión de secretos).
4. `docs/migration.md`: costos reales (~USD 25–50/mes por Cloud SQL 24/7, §12), alternativas (ventana de demo `apply`/`destroy` vs quedarse en `plan`), y decisiones abiertas que deben cerrarse antes de aplicar (D10 / §17.2: Gemini vía Vertex; §17.3: embeddings Vertex text-embedding vs `bge-m3` autoalojado; §17.4: índice baked vs GCS).
5. **No aplicar sin visto bueno** (política heredada del base: los `*.tf` se revisan antes de `apply`).

## Salidas

- `infra/terraform/` adaptado + `docs/migration.md`.

## Exit criteria (M9, acotado)

- [ ] `terraform fmt -check` y `terraform validate` sin errores; `terraform plan` válido si hay credenciales (si no, fmt+validate como mínimo, documentado).
- [ ] Cero secretos en el repo (`scripts/secrets_audit.sh` cubre `infra/`).
- [ ] `docs/migration.md` completo: costos, alternativas y decisiones abiertas antes de `apply`.

## Verificación

```bash
cd infra/terraform && terraform fmt -check && terraform validate
scripts/secrets_audit.sh
```

Registrar en heartbeat: resultado de validate/plan (o por qué no se pudo), y las decisiones abiertas vigentes.
