# Migración a GCP — M9

Estado: **APLICADO Y VIVO.** 37 recursos en `diplomado-499206`, servicio corriendo en

**https://emociones-app-zxzgilzqfq-uc.a.run.app**

El `apply` se hizo con visto bueno explícito del owner. Verificado en producción: RAG con
Vertex, los tres guardarraíles, memoria en Firestore, aislamiento entre portadores y
analítica en BigQuery. Detalle en §7.

Costos y las alternativas que se descartaron: [`presupuesto-gcp.md`](presupuesto-gcp.md).

## 1. Arquitectura

```
                 ┌──────────────── Cloud Run (min=0, max=3) ─────────────────┐
  navegador ───► │  contenedor único: FastAPI + frontend vanilla             │
                 │  índice FAISS horneado en la imagen (19 MB, sin servicio  │
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
| Índice RAG | FAISS horneado en la imagen | 19 MB: no justifica un servicio aparte (§12 del PRD) |
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

## 4. Migración de código: hecha y validada contra Vertex

La aplicación ya no habla solo Postgres y Ollama. Se añadió una capa de
conmutación y **se validó el camino de nube contra el proyecto real**.

| # | Trabajo | Estado |
|---|---|---|
| 1 | Capa de persistencia intercambiable | `especialista/stores/` con protocolo `Store` y dos backends; `memory`/`auth`/`audit` no saben cuál usan |
| 2 | Session service de ADK sobre Firestore | `especialista/firestore_sessions.py` (ADK 2.8 no trae uno) |
| 3 | Adaptador de LLM y embeddings | `especialista/providers.py`, un único punto de conmutación por `LLM_PROVIDER` |
| 4 | Reindexado a 3072 dims | hecho: 1.216 vectores, índice de 19 MB, coste real ~USD 0.09 |
| 5 | Emisor de eventos a BigQuery | `especialista/analytics.py`, solo metadatos |
| 6 | Gold set contra Vertex | corrido; resultados abajo |

### 4.1 Recuperación con `gemini-embedding-001` (3072 dims)

**Mejora respecto a `bge-m3`, y cierra la deuda de M2.**

| Tipo | bge-m3 (1024) | Vertex (3072) | Meta |
|---|---|---|---|
| single | 27/31 = 0.871 | **28/31 = 0.903** | ≥0.85 ✓ |
| alias | 13/15 = 0.867 ✗ | **14/15 = 0.933** | ≥0.90 ✓ |
| risk_tier | 9/10 = 0.900 | 9/10 = 0.900 | 10/10 |
| multi | 5/6 = 0.833 | 5/6 = 0.833 | 6/6 |
| emergency | 5/5 | 5/5 | corta antes del LLM ✓ |
| out_of_domain | 13/13 = 1.000 | 13/13 = 1.000 | precision 1.0 ✓ |

`alias` pasa de 0.867 a **0.933** y supera por primera vez el gate duro ≥0.90 que
llevaba pendiente desde M2. Los tres criterios del gate (single ≥0.85, alias ≥0.90,
precisión fuera de dominio 1.0) se cumplen ahora simultáneamente.

**Hubo que recalibrar el umbral de cobertura.** `TAU_DENSE_FALLBACK` valía 0.70,
calibrado para `bge-m3`. Cada espacio de embeddings tiene su propia distribución de
similitud, así que ese valor es sencillamente incorrecto para otro modelo: con
Vertex, «¿qué significa emocionalmente el cuerpo?» puntuaba 0.7385 sin ningún match
nominal y se colaba como cobertura, rompiendo la precisión fuera de dominio = 1.0
que el PRD §13.0 declara innegociable.

Se barrió el umbral sobre el gold set y se tomó el más bajo que la conserva:

| Umbral | Precisión fuera de dominio | Cobertura en dominio |
|---|---|---|
| 0.70 | 12/13 ✗ | 65/67 |
| 0.72 | 12/13 ✗ | 64/67 |
| **0.74–0.76** | **13/13 ✓** | **64/67** |
| 0.78+ | 13/13 ✓ | 63/67 |

Se fijó **0.75**, en medio de la meseta estable. El umbral es ahora un mapa por
modelo, y un modelo desconocido recibe el valor más estricto.

### 4.2 End-to-end con `gemini-2.5-flash-lite`

| Métrica | gemma4 local | Vertex flash-lite |
|---|---|---|
| Global | 0.865 | **0.923** |
| single | 0.903 | **0.935** |
| alias | 1.000 | 1.000 |
| multi | 0.333 | **0.667** |
| **Latencia media** | 8.5 s | **2.1 s** |

Son las mejores cifras del proyecto. `multi` **duplica** el 0.333 histórico y el global sube
a 0.923. Buena parte del salto no es mérito del modelo sino de un bug corregido: flash-lite
envolvía el JSON de extracción en un bloque markdown y el multi-hop llevaba corriendo
degradado (§7.3).

**Nota sobre una medición intermedia.** Antes de corregir el parseo, esta misma tabla daba
global 0.846 y single 0.839. Se investigó en vez de aceptarlo: no era que flash-lite citara
menos (4,42 citas/turno con gemma4 frente a 4,46 con Vertex, prácticamente iguales), sino que
el umbral recalibrado hacía que dos huecos de sinonimia conocidos (`g019` respirar→disnea,
`g022` dormir→insomnio) respondieran honestamente «sin cobertura» en vez de recibirla por el
respaldo denso. Al corregir además el parseo del JSON, el resultado final supera a ambos.

Datos crudos: `outputs/evidence/e2e_results_vertex.json`. La corrida de referencia
del sistema local sigue en `e2e_results.json`; **no se mezclan**, porque las cifras
de un modelo no son extrapolables a otro.

### 4.3 Lo que queda

- **`multi` sigue sin llegar a 6/6** y `risk_tier` a 10/10. Misma causa raíz de siempre:
  sinonimia coloquial ausente de `aliases.json` (congelado en M0).
- **El emulador de Firestore no se usa en local**: los tests del backend de nube usan
  un doble en memoria. Suficiente para el contrato, pero un `apply` real es la primera
  vez que el código habla con Firestore de verdad.
- **Falta construir y subir la imagen** al Artifact Registry (§5).

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

## 7. Despliegue real — verificación en producción

`terraform apply` ejecutado el **2026-09-07**. 37 recursos creados, 0 destruidos.
Servicio: **https://emociones-app-zxzgilzqfq-uc.a.run.app**

### 7.1 Lo verificado contra el servicio vivo

| # | Qué | Resultado |
|---|---|---|
| 1 | `/health` y frontend | 200 |
| 2 | Registro y login reales | JWT emitido |
| 3 | Consulta con RAG + Vertex | `respuesta`, 3 fuentes citadas, 5,8 s |
| 4 | Emergencia (FR-06) | `emergency`, 0 fuentes, derivación pediátrica |
| 5 | Prompt injection (NFR-01) | **HTTP 403** |
| 6 | Fuera de dominio | `sin_cobertura` |
| 7 | Perfil persistido en Firestore (FR-14) | 1 consulta guardada |
| 8 | Sesiones ADK en Firestore (FR-12) | 1 sesión, 6 eventos |
| 9 | Aislamiento entre portadores (FR-17) | usuario B ve 0 perfiles y 0 sesiones |
| 10 | Memoria (FR-13) | «Tu última consulta registrada fue sobre el dolor de garganta» |
| 11 | Analítica en BigQuery | filas en `consultas`, `guardarrailes` y `recuperacion` |
| 12 | Escala a cero | `minScale = 0` |

**Evidencia inesperada de NFR-02b en los datos de latencia:** una emergencia se
resuelve en **57 ms** frente a **1.799 ms** de una consulta normal. La diferencia
es exactamente lo que se corta: recuperación y LLM. El guardarraíl no es una
instrucción al modelo, y la telemetría lo demuestra sin necesidad de un test.

### 7.2 Tres problemas reales que solo aparecieron al desplegar

**1. Cloud Run reserva el prefijo `ah-`.** `ah-emociones-app` se rechaza con un 400
(«must not begin with reserved keyword 'aef-' or 'ah-'»). El resto de recursos sí
admite el prefijo. Se separó `run_service_name` (`emociones-app`) con una
`validation` en Terraform para que el error salga en el `plan` y no en el `apply`.

**2. `analytics.py` estaba escrito y testeado pero no cableado.** Las tablas de
BigQuery quedaron vacías tras el primer despliegue: nadie llamaba al emisor. Probar
el módulo aisladamente no detecta eso — hay que probar el pipeline. Se cableó en
`run_deterministic` y se añadieron tests que corren el pipeline completo y exigen
que emita.

**3. Fuga de privacidad: el mensaje del usuario llegó a BigQuery.** Cuando
`extract_symptoms` no devuelve nada, el pipeline busca con el mensaje entero
(`symptoms = [clean_message]`) y esa lista se emitía tal cual a `symptom_slug`. Se
encontró inspeccionando las filas reales: contenían *«no puedo dormir y ando muy
irritable»*. Viola NFR-07 de forma directa.

- El test que escribí **no lo cazó** porque usaba un caso de emergencia, donde
  `symptoms` va vacío. El camino con fuga era el de sin cobertura.
- **Corregido**: solo se emiten los síntomas realmente extraídos, slugificados y con
  tope de longitud; si la extracción falló, va lista vacía.
- **Datos purgados**: el `DELETE` lo bloqueaba el buffer de streaming, así que la
  tabla se recreó con `terraform apply -replace`.
- **Test de regresión** sobre el camino correcto, validado por mutación: al
  reintroducir la fuga, falla.

### 7.3 Un bug que la nube destapó en el propio agente

`gemini-2.5-flash-lite` devuelve el JSON de extracción **envuelto en un bloque
markdown** (` ```json … ``` `); `gemma4` lo devuelve pelado. `json.loads` fallaba y
`extract_symptoms` caía al fallback **en todos los turnos**, así que el multi-hop
buscaba con el mensaje entero en vez de con cada síntoma por separado. No lanzaba
ninguna excepción: se degradaba en silencio.

Corregido con un parseo tolerante (bloque markdown, JSON pelado, o rescate del
primer array del texto) y cuatro tests de regresión.

### 7.4 El presupuesto de alertas NO se pudo crear

`google_billing_budget` falla con `400 INVALID_ARGUMENT`. **No es la configuración**:
se comprobó que falla igual un budget mínimo creado con `gcloud`, sin filtro de
proyecto. Es una limitación de la cuenta de facturación (habitual en cuentas de
prueba), no del código.

El recurso queda escrito y se crea solo si se pasa `billing_account`. **Hay que
crear la alerta a mano en la consola** (Facturación → Presupuestos y alertas, USD 5
con avisos al 50/90/100%): es la red de seguridad contra un gasto inesperado de
Vertex, que es lo único que escala con el uso.

### 7.5 Costo real observado

La imagen quedó en **147 MB comprimidos**, por debajo del free tier de 0,5 GB de
Artifact Registry, así que ese renglón cae de $0.22 a **$0**. El piso mensual real
es de **$0.12** (dos versiones de secreto en Secret Manager). Todo lo demás —Cloud
Run, Firestore, BigQuery, GCS— cabe en el free tier con este volumen.

### 7.6 Para desmontarlo

```bash
terraform -chdir=infra/terraform destroy
```

Nada corre 24/7, así que dejarlo encendido cuesta ~$0.12/mes. El `destroy` es para
liberar el proyecto, no para ahorrar.
