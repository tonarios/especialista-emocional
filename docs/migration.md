# Migración a GCP — M9

Estado: **Terraform escrito, `fmt`/`validate` en verde y `plan` ejecutado contra el proyecto
real `diplomado-499206` — 37 recursos a crear, 0 a cambiar, 0 a destruir. No se ha aplicado
nada.** El `apply` requiere visto bueno explícito del owner (política heredada del repo base)
y, antes, cerrar la migración de código de §4.

Costos y las alternativas que se descartaron: [`presupuesto-gcp.md`](presupuesto-gcp.md).

## 1. Arquitectura

```
                 ┌──────────────── Cloud Run (min=0, max=3) ─────────────────┐
  navegador ───► │  contenedor único: FastAPI + frontend vanilla             │
                 │  índice FAISS horneado en la imagen (~21 MB, sin servicio │
                 │  de vectores)                                             │
                 └───┬───────────────┬──────────────────┬────────────────────┘
                     │               │                  │
              Vertex AI         Firestore           BigQuery
        gemini-2.5-flash-lite   auth · perfiles     métricas y metadatos
        gemini-embedding-001    sesiones ADK        (NUNCA texto de chats)
        (SA, sin API key)       auditoría
```

Deliberadamente **no hay** Cloud SQL, VPC Connector, pgvector ni servicio de vectores: son
justo los componentes que corren 24/7 y no escalan a cero.

| Recurso | Elección | Por qué |
|---|---|---|
| Cómputo | Cloud Run, `min_instances = 0` | única forma de pagar cero sin tráfico |
| LLM | `gemini-2.5-flash-lite` | el más barato de la familia: $0.10 / $0.40 por 1M tok |
| Embeddings | `gemini-embedding-001`, 3072 dims | sin truncar (decisión del owner) |
| Auth + memoria | Firestore Native | cabe en el free tier; Cloud SQL costaría ~$9.83/mes en reposo |
| Índice RAG | FAISS horneado en la imagen | 21 MB: no justifica un servicio aparte (§12 del PRD) |
| Analítica | BigQuery, particionado por día | free tier; solo metadatos |
| Secretos | Secret Manager (2) | `JWT_SECRET` y la sal del hash analítico |
| Estado de TF | GCS privado con versionado | el state lleva secretos en claro |

**Vertex se autentica por service account, no por clave de API.** Eso elimina el secreto
`gemini-api-key` que sí tenía el repo base: un secreto menos que rotar y que filtrar.

## 2. Qué provisiona el Terraform (37 recursos)

| Tipo | n |
|---|---|
| `google_project_service` | 9 |
| `google_bigquery_table` | 4 |
| `google_project_iam_member` | 4 |
| `google_firestore_index` | 2 |
| `google_secret_manager_secret` (+ version, + iam) | 2 × 3 |
| `google_cloud_run_v2_service` (+ iam) | 1 + 1 |
| `google_firestore_database` | 1 |
| `google_bigquery_dataset` (+ iam) | 1 + 1 |
| `google_artifact_registry_repository` (+ iam) | 1 + 1 |
| `google_service_account` | 1 |
| `google_storage_bucket` (tfstate) | 1 |
| `google_billing_budget` | 1 |
| `random_password` | 2 |

Ficheros: `main.tf` (providers y APIs), `variables.tf`, `data.tf` (Firestore + BigQuery),
`iam.tf`, `registry.tf` (Artifact Registry + secretos), `run.tf`, `budget.tf`, `state.tf`,
`outputs.tf`.

## 3. Seguridad de la infraestructura

Verificada con **17 aserciones sobre el `plan` resuelto**, no sobre el texto de los `.tf`
(`tests/test_infra_security.py`). Se auditó el plan porque un comentario no engaña a un plan.

| Propiedad | Cómo se comprueba |
|---|---|
| Sin roles de administración en el runtime | lista negra de 10 roles (`owner`, `editor`, `*.admin`…) |
| Roles de proyecto exactamente los 4 justificados | igualdad estricta, no subconjunto |
| Secretos y BigQuery con alcance **por recurso** | falla si aparecen a nivel proyecto |
| Sin claves descargables de service account | no existe `google_service_account_key` |
| Vertex sin clave de API | ningún secreto que parezca `*api*key*` |
| `allUsers` solo en el invoker de Cloud Run | busca `allUsers` en el plan **entero** |
| Bucket del estado privado | `public_access_prevention=enforced` + acceso uniforme + versionado |
| **BigQuery no admite texto de chats** | lista negra de 20 nombres de campo (`mensaje`, `prompt`, `email`…) |
| El usuario en analítica es un hash con sal | `user_hash` presente, `email`/`user_id` ausentes, sal en Secret Manager |
| Tablas de eventos particionadas por día | sin partición, cada consulta escanea todo |
| Cloud Run escala a cero | `min_instance_count == 0` y `cpu_idle == true` |
| Tope de escalado | `0 < max_instance_count <= 10` |
| Presupuesto con alertas | umbrales 50/90/100% + alerta sobre gasto **previsto** |
| Registry con política de limpieza | acciones `KEEP` y `DELETE` presentes |
| Sin Cloud SQL ni VPC Connector | ningún recurso que corra 24/7 |
| Secretos marcados como sensibles en el plan | `after_sensitive.secret_data == true` |
| `JWT_SECRET` inyectado por referencia | nunca como valor literal en el env de Cloud Run |

**Los tests se validaron por mutación:** al inyectar en el plan `roles/owner`, un campo
`mensaje` en BigQuery y `min_instances = 1`, fallaron 5 aserciones; al restaurar el plan,
volvieron las 17 en verde. No pasan vacías.

`scripts/secrets_audit.sh` se extendió con 4 comprobaciones de infraestructura (8/8 en verde):
sin `.tfstate` ni `.tfvars` versionados, sin literales de secreto en los `.tf`, sin claves de
service account, y sin valores sensibles expuestos en el plan.

Se corrigió además que `.terraform.lock.hcl` estuviera en `.gitignore`: ese fichero fija los
hashes de los providers y **debe** commitearse, o `init` puede resolver una versión distinta
a la auditada.

Reproducir todo: `scripts/infra_audit.sh` (fmt → validate → plan real → 17 aserciones →
auditoría de secretos). Evidencia en `outputs/evidence/{tfplan.json,tfplan.txt,infra_audit.txt,secrets_audit.txt}`.

## 4. Lo que falta antes de un `apply` útil

El Terraform está listo, pero **la aplicación todavía habla Postgres y Ollama**. Aplicar hoy
levantaría infraestructura correcta con un contenedor que no arranca contra ella. Pendiente:

| # | Trabajo | Alcance |
|---|---|---|
| 1 | Capa de persistencia sobre Firestore | reescribir `memory.py`, `auth.py` y `audit.py`; seleccionar por `STORAGE_BACKEND` (`postgres` local / `firestore` nube) |
| 2 | Session service de ADK sobre Firestore | ADK 2.8 trae `database_`, `sqlite_`, `in_memory_` y `vertex_ai_`, pero **no** Firestore: hay que implementar `BaseSessionService` |
| 3 | Adaptador de LLM a Vertex | `run_deterministic` llama hoy a `/api/chat` de Ollama con `think:false`; añadir rama Vertex por `LLM_PROVIDER` |
| 4 | Adaptador de embeddings a Vertex | `index.py` usa `/api/embed` de Ollama; añadir `gemini-embedding-001` |
| 5 | Reindexar a 3072 dims | ~$0.09 y ~21 MB de índice; el hash de corpus ya invalida la caché solo |
| 6 | Emisor de eventos a BigQuery | Storage Write API en el mismo turno; solo metadatos (§3) |
| 7 | Volver a correr el gold set contra Vertex | las métricas actuales son de `gemma4` local; **no** son extrapolables |

Estimación: ~350 líneas de código nuevo más el reindexado. El punto 7 no es opcional: cambiar
de modelo y de espacio de embeddings puede mover el recall en cualquier dirección, y el
reporte no debe heredar cifras de otro modelo.

## 5. Procedimiento de despliegue (cuando se autorice)

```bash
# 1. Estado remoto (una sola vez): crear el bucket antes de activar el backend
terraform -chdir=infra/terraform apply -target=google_storage_bucket.tfstate
#    luego añadir el bloque backend "gcs" y `terraform init -migrate-state`

# 2. Imagen (perfil cloud: sin Ollama ni litellm, 582 MB)
gcloud auth configure-docker us-central1-docker.pkg.dev
docker build --build-arg EXTRA=cloud --platform linux/amd64 \
  -t us-central1-docker.pkg.dev/diplomado-499206/ah-emociones/app:latest .
docker push us-central1-docker.pkg.dev/diplomado-499206/ah-emociones/app:latest

# 3. Revisar el plan y aplicar SOLO con visto bueno
scripts/infra_audit.sh          # fmt + validate + plan + 17 aserciones de seguridad
terraform -chdir=infra/terraform apply

# 4. Para desmontar (opción C del presupuesto: ventana de demo)
terraform -chdir=infra/terraform destroy
```

El orden importa: Artifact Registry debe existir antes del `push`, así que el primer `apply`
puede acotarse con `-target=google_artifact_registry_repository.docker`.

## 6. Decisiones abiertas que quedan

| Ref | Pregunta | Estado |
|---|---|---|
| §17.9 | ¿El diplomado exige despliegue vivo? | **abierta** — determina si se llega a `apply` o basta el plan |
| §17.2 | LLM de producción | **cerrada**: Gemini 2.5 Flash-Lite vía Vertex |
| §17.3 | Embeddings en nube | **cerrada**: `gemini-embedding-001` a 3072 dims |
| §17.4 | Ubicación del índice | **cerrada**: horneado en la imagen |
| §12 | Cloud SQL vs alternativa | **cerrada**: Firestore (opción A del presupuesto) |
| — | NFR-10 (conexión privada y autenticada) | **se ajusta**: con Firestore no hay IP privada de VPC; el acceso es por IAM y TLS con la identidad del service account, sin credencial compartida ni superficie de red expuesta |

El último punto es una desviación consciente del PRD: NFR-10 se escribió pensando en Cloud
SQL. Firestore no tiene "IP privada" porque no tiene IP: el control es IAM, que para este
caso es una garantía más fuerte que una regla de red, y sin el costo del VPC Connector.
