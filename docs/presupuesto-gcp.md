# Presupuesto GCP — antes de crear nada (M9)

> **Nada se ha creado todavía.** Este documento existe para confirmar costos **antes** de
> escribir el Terraform definitivo y mucho antes de cualquier `apply`.
> Precios consultados el **2026-09-06** (región tier 1, `us-central1`). Fuentes al final.

## 1. Restricciones que fijó el owner

| # | Restricción | Cómo se cumple |
|---|---|---|
| 1 | Costos mínimos | Todo lo que tiene *free tier* se dimensiona para caber dentro |
| 2 | Modelos más baratos de Vertex | **Gemini 2.5 Flash-Lite** ($0.10 / $0.40 por 1M tok) |
| 3 | Embeddings de Vertex si hacen falta | **gemini-embedding-001** ($0.15 por 1M tok), **3072 dims** (sin truncar, decisión del owner) |
| 4 | Sin bases vectoriales | Índice **FAISS horneado en la imagen** (~15 MB a 3072 dims); cero servicios de vectores |
| 5 | Escala a cero | Cloud Run con `min_instances = 0` |
| 6 | Análisis en BigQuery | Dataset de métricas + eventos; dentro del free tier |

## 2. Consumo real medido (no estimado a ojo)

Medido sobre este repo, no sacado de un blog:

| Magnitud | Valor | Cómo se obtuvo |
|---|---|---|
| Prompt por turno | **~3.070 tokens** | `system_instruction.md` (2.426 ch) + contexto RAG k=5 (media 9.229 ch) ÷ 3,8 ch/tok |
| Respuesta por turno | ~400 tokens | media de 1.500 ch en `e2e_results.json` |
| Llamada de extracción de síntomas | ~300 in / 50 out | 1 llamada estructurada por turno (§9) |
| **Total por turno** | **~3.400 in / ~450 out** | |
| Corpus completo | 2.264.925 ch ≈ **595k tokens** | 1.265 `.md` en `data/` |
| Índice FAISS | 11 MB hoy (1024 dims); **~21 MB** al reindexar a 3072 | se hornea en la imagen |
| Imagen Docker (cloud) | **582 MB** | `agent-app:cloud`, tras adelgazar (§4) |

**Costo Vertex por turno:**
`3.400 × $0.10/1M` + `450 × $0.40/1M` + `~15 tok de embedding × $0.15/1M` = **$0.00052 / turno**
→ **$0.52 por cada 1.000 turnos.**

**Reindexado completo con embeddings de Vertex (una sola vez):**
`595k tokens × $0.15/1M` = **$0.09**. Se puede repetir sin pensarlo.

## 3. Lo que es gratis con este volumen

| Servicio | Free tier mensual | Nuestro consumo con 5.000 turnos/mes | ¿Cabe? |
|---|---|---|---|
| Cloud Run vCPU | 180.000 vCPU-s | ~25.000 vCPU-s (1 vCPU × 5 s × 5.000) | ✅ 14% |
| Cloud Run memoria | 360.000 GiB-s | ~50.000 GiB-s (2 GiB × 5 s × 5.000) | ✅ 14% |
| Cloud Run peticiones | 2.000.000 | 5.000 | ✅ 0,25% |
| Firestore lecturas | 50.000/día | ~15.000/día en el peor caso | ✅ |
| Firestore escrituras | 20.000/día | ~2 por turno | ✅ |
| Firestore almacenamiento | 1 GiB | < 10 MB | ✅ |
| BigQuery consultas | 1 TiB/mes | < 1 GiB escaneado | ✅ 0,1% |
| BigQuery almacenamiento | 10 GiB/mes | < 100 MB | ✅ |
| GCS (estado de Terraform) | 5 GB en regiones US | < 1 MB | ✅ |

**Cloud Run sale gratis incluso con 5.000 turnos al mes.** El free tier es por cuenta de
facturación y por mes, no promocional.

## 4. Lo que sí cuesta, pase lo que pase

| Concepto | Cálculo | Mensual |
|---|---|---|
| Artifact Registry | (0,58 GB − 0,5 GB gratis) × $0.10/GB | **$0.01** |
| Secret Manager | 2 versiones activas (`JWT_SECRET`, sal de analítica) × $0.06 | **$0.12** |
| **Piso con CERO uso** | | **$0.13** |

> **Adelgazado ya hecho (2026-09-06).** La imagen pasó de **2,7 GB a 582 MB** (−78%) y con eso
> Artifact Registry cae de $0.22 a $0.01/mes. Dos causas, ambas corregidas:
> - un `chown -R appuser /app` **después** de crear el venv duplicaba el árbol entero en una
>   capa de **682 MB**; ahora el build es multi-stage y el usuario se crea antes de copiar;
> - `scipy` (71 MB) estaba en las dependencias y **no lo usaba ningún fichero**; `litellm`
>   (92 MB, arrastra botocore, openai, tokenizers y huggingface_hub) solo lo necesita el
>   camino local con Ollama. Ambos salen del perfil `cloud` (`pyproject.toml` → extras
>   `local` / `cloud`).
>
> Beneficio colateral: el arranque en frío de Cloud Run mejora mucho, que es el precio real
> de escalar a cero.

## 5. Las tres opciones — la decisión está en dónde vive auth + memoria

Todo lo anterior es común. Lo único que mueve la aguja es **dónde se guardan usuarios,
perfiles y sesiones ADK**, porque es lo único que puede no escalar a cero.

### Opción A — Firestore (escala a cero de verdad) ✅ recomendada

| Recurso | Mensual |
|---|---|
| Cloud Run | $0 |
| Firestore | $0 |
| BigQuery | $0 |
| Artifact Registry + Secret Manager | $0.13 |
| Vertex — 500 turnos | $0.26 |
| **Total** | **≈ $0.39/mes** |
| Con 5.000 turnos | ≈ $2.73/mes |
| **Con cero uso** | **$0.13/mes** |

**Costo real de esta opción no es dinero, es código.** Hay que reemplazar Postgres en
`memory.py`, `auth.py` y `audit.py`, y escribir un *session service* de ADK sobre Firestore
(ADK 2.8 trae `database_session_service`, `sqlite_`, `in_memory_` y `vertex_ai_`, pero
**no** uno de Firestore). Estimo ~300-400 líneas nuevas y usar el emulador de Firestore en
local para no divergir del stack de Docker.

### Opción B — Cloud SQL (fiel al PRD §12, cero cambios de código)

| Recurso | Mensual |
|---|---|
| Todo lo de la opción A salvo Firestore | $0.39 |
| Cloud SQL `db-f1-micro` (compute, 24/7) | ~$8.00 |
| 10 GB SSD | ~$1.70 |
| **Total** | **≈ $10.09/mes** |
| **Con cero uso** | **≈ $9.83/mes** |

`db-f1-micro` es *shared-core*, solo edición Enterprise, **sin SLA** y **sin descuentos por
uso comprometido**. No escala a cero: se paga aunque nadie entre. Incumple la restricción 5.

> **Variante B′ — instancia detenida entre demos.** Una instancia de Cloud SQL *parada* no
> factura compute, solo almacenamiento: **~$1.70/mes** en reposo, y se arranca (2-3 min)
> para cada demo. Conserva el código tal cual y baja el piso 6×. Es un arranque manual, no
> automático: no es "escala a cero", es "apagado entre usos".

### Opción C — Ventana de demo (`apply` → evidencia → `destroy`)

Opción B levantada 3 horas para capturar la evidencia en la nube y destruida después:
Cloud SQL `$8 × 3/730` = $0.03 · Vertex ~$0.05 · resto ~$0.01 → **menos de $0.20 en total**.

Es lo que el PRD §12 propone si el diplomado no exige despliegue vivo (§17.9, aún abierta).

### Comparativa

| | A — Firestore | B — Cloud SQL | B′ — detenida | C — ventana |
|---|---|---|---|---|
| Piso mensual (sin uso) | **$0.13** | $9.83 | $1.83 | ~$0 |
| Con 500 turnos/mes | **$0.39** | $10.09 | $2.09 | — |
| Escala a cero | ✅ | ❌ | ⚠️ manual | ✅ |
| Cambios de código | ~350 líneas | ninguno | ninguno | ninguno |
| Fiel al PRD §12 | se desvía | ✅ | ✅ | ✅ |

## 6. BigQuery — análisis de la información

Cabe entero en el free tier (1 TiB de consulta y 10 GiB de almacenamiento al mes), así que
**cuesta $0** con este volumen. Lo que hay que decidir no es el precio sino **qué se manda**.

**Restricción dura (NFR-07 + FR-05b):** a BigQuery van **métricas y metadatos**, nunca el
texto de los chats. Son datos de salud; el PRD prohíbe loguear contenido de conversaciones.

Tablas propuestas:

| Tabla | Columnas | Para qué |
|---|---|---|
| `consultas` | `ts`, `user_hash`, `symptom_slug`, `term_slug[]`, `risk_tier`, `kind`, `latency_ms` | términos más consultados, distribución de riesgo, latencia |
| `recuperacion` | `ts`, `query_hash`, `k`, `hit_lexico`, `sin_cobertura`, `top_slugs[]` | dónde falla el RAG en producción (la deuda de sinonimia) |
| `guardarrailes` | `ts`, `tipo` (emergencia/injection/prescripción), `grupo` | cuántas veces disparan y cuáles |
| `eval` | `run_id`, `ts`, `tipo`, `recall`, `ci95_low`, `ci95_high`, `n` | serie histórica de las corridas de `evidence.sh` |

`user_hash` es un hash con sal del email, no el email: permite contar usuarios distintos y
medir retención sin guardar identidad en el almacén analítico.

**Cómo llegan los datos** (depende de la opción de arriba):
- **Opción A:** el backend escribe el evento a BigQuery con la Storage Write API en el mismo
  turno. Sin ETL, sin job programado. Es lo más simple.
- **Opción B:** igual, o consulta federada desde BigQuery a Cloud SQL (`EXTERNAL_QUERY`).

La tabla `eval` es interesante aparte del producto: convierte las métricas de `evidence.sh`
en una serie temporal, así se ve si el recall se degrada entre corridas en vez de tener solo
la foto de la última.

## 7. Riesgos de costo (lo que puede dispararse)

| Riesgo | Impacto | Mitigación |
|---|---|---|
| Bucle de reintentos contra Vertex | el gasto de Vertex es el único proporcional al uso | tope de reintentos + **presupuesto con alerta** en Terraform |
| Cloud Run sin `max_instances` | una ráfaga escala y consume el free tier | `max_instances = 3` (suficiente para demo) |
| Imagen de 2,7 GB acumulando versiones | Artifact Registry crece $0.10/GB/mes | **cleanup policy**: conservar 3 versiones |
| Cloud SQL olvidado encendido (opción B) | ~$10/mes indefinidos | alerta de presupuesto + recordatorio de `destroy` |
| Reindexado en bucle | $0.09 por pasada, nada grave | cacheado por hash de corpus (ya implementado) |

**Se propone incluir en el Terraform un `google_billing_budget` de USD 5/mes con alertas al
50/90/100%.** Cuesta $0 y es la red de seguridad de todo lo anterior.

## 8. Detalle de precios usados

| Recurso | Precio | Free tier |
|---|---|---|
| Gemini 2.5 Flash-Lite | $0.10 / 1M in · $0.40 / 1M out | — |
| gemini-embedding-001 | $0.15 / 1M tokens | — |
| Cloud Run (tier 1) | $0.000024/vCPU-s · $0.0000025/GiB-s · $0.40/M req | 180k vCPU-s · 360k GiB-s · 2M req |
| Cloud SQL `db-f1-micro` | ~$8/mes + ~$0.17/GB SSD | — |
| Firestore | por operación | 50k lec/día · 20k esc/día · 1 GiB |
| BigQuery on-demand | $6.25/TiB escaneado · $0.02/GiB-mes | 1 TiB/mes · 10 GiB |
| Artifact Registry | $0.10/GB-mes | 0,5 GB |
| Secret Manager | $0.06 por versión activa/mes | — |
| GCS Standard (US) | $0.020/GB-mes | 5 GB-mes |

### Fuentes

- [Gemini API Pricing — BenchLM (sep 2026)](https://benchlm.ai/google/api-pricing)
- [Vertex AI generative AI pricing](https://cloud.google.com/vertex-ai/generative-ai/pricing)
- [Cloud Run pricing](https://cloud.google.com/run/pricing)
- [Cloud SQL pricing — Bytebase](https://www.bytebase.com/dbcost/cloudsql-pricing/)
- [Firestore pricing](https://cloud.google.com/firestore/pricing)
- [BigQuery pricing](https://cloud.google.com/bigquery/pricing)
- [Artifact Registry pricing](https://cloud.google.com/artifact-registry/pricing)
- [Gemini Embedding GA — Google Developers Blog](https://developers.googleblog.com/gemini-embedding-available-gemini-api/)
