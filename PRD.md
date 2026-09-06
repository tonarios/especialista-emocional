# PRD — Agente Especialista en Enfermedades Emocionales (ADK + RAG + Memoria + Auth)

| Campo | Detalle |
|---|---|
| **Producto** | Agente conversacional especialista en enfermedades emocionales, con RAG sobre un diccionario emocional, memoria persistente y autenticación simple |
| **Estado** | Borrador aprobado para implementación |
| **Base técnica** | `ah-grupo-fundador` (Google ADK 2.x + FastAPI + PostgreSQL + frontend vanilla) |
| **Ubicación** | `/Users/data_sci/Documents/personal/diplomado_ia/agent` (el `data/` con los `.md` ya vive aquí) |
| **Fecha** | 2026-09-05 |

---

## 1. Resumen ejecutivo

Construir un **agente conversacional** que, ante la consulta de un usuario sobre un síntoma o enfermedad, recupera del **diccionario emocional** (1.265 términos en `data/*.md`) los significados emocionales relevantes y devuelve una **interpretación emocional integrada** (nunca un diagnóstico médico), citando las fuentes. El agente **relaciona varios síntomas** cuando el usuario describe más de uno (multi-hop).

Se construye **partiendo del repo `ah-grupo-fundador`**, reutilizando su autenticación (email+clave + JWT), memoria (PostgreSQL), guardrails anti prompt-injection, rate-limit, auditoría, frontend vanilla y arnés de evaluación. Lo **nuevo** es la capa **RAG** (**FAISS** + embeddings) y el **dominio** (enfermedades emocionales).

Ejecución **local** con **LLM `gemma4` vía Ollama** (ya instalado) y **embeddings `bge-m3`**. Migración posterior a **GCP con recursos mínimos** (Cloud Run + Cloud SQL + Secret Manager + Vertex AI como LLM recomendado, aún TBD).

## 2. Objetivos y no-objetivos

### Objetivos
- **O1.** Responder consultas del usuario con la interpretación emocional del diccionario, respaldada por RAG y con **citas de fuente** visibles.
- **O2.** **Relacionar múltiples síntomas** del usuario en una lectura integrada cuando aplique.
- **O3.** **Memoria persistente**: recordar la conversación y el historial de consultas del usuario entre sesiones y reinicios.
- **O4.** **Autenticación simple** segura (registro/login + token), con aislamiento real por usuario.
- **O5.** Seguridad de extremo a extremo: anti **prompt-injection**, anti **SQL-injection**, rate-limit, secretos fuera del repo, y **guardarraíles de seguridad médica** (disclaimer + escalamiento de emergencias).
- **O6.** Frontend **vanilla** (login + chat con chips de fuentes).
- **O7.** Operación por **Docker + Makefile** (contenedor único back+front).
- **O8.** **Evidencia** de registro de usuarios y memoria, más arnés completo de QA/eval (GIFs, métricas, PDF).
- **O9.** Camino claro para **migrar a GCP** con recursos mínimos.

### Naturaleza del proyecto

**Proyecto académico de diplomado.** No se despliega a usuarios reales ni se distribuye públicamente. Las cuentas de prueba son propias o sintéticas; no se procesan datos de salud de terceros.

Esto **no** relaja los guardarraíles médicos: el corpus es un cuerpo de creencias (linaje biodescodificación / nueva medicina germánica), no evidencia clínica, y el sistema debe comportarse correctamente ante consultas de riesgo porque **eso es precisamente lo que se evalúa**. Sí acota el alcance: no hace falta consentimiento formal, retención legal, ni revisión clínica externa.

Lo que sí cambia es la **prioridad de la evidencia**: en un contexto académico, el arnés de QA/eval y el reporte no son "extras" — son el entregable que se califica (ver §15).

### No-objetivos
- **NO** es un producto para usuarios reales; no hay operación ni soporte más allá de la demo.
- **NO** dar diagnóstico médico real, prescribir, ni recomendar tratamientos médicos.
- **NO** OAuth / login social, verificación por email, ni recuperación de contraseña.
- **NO** multi-idioma (solo español).
- **NO** panel de administración ni gestión de contenido.
- **NO** pagos ni facturación.

## 3. Contexto y antecedentes

- **Datos (RAG)**: `data/*.md` — 1.265 términos ya extraídos. Frontmatter `title/slug/letter` completo en los 1.265 (verificado). El **cuerpo NO tiene estructura uniforme**: las secciones aparecen de forma desigual y ningún parser puede asumirlas.

  | Sección | Documentos | % |
  |---|---:|---:|
  | `Tratamientos emocionales` | 1.190 | 94% |
  | `Analogía` | 1.109 | 88% |
  | `Conflicto` | 1.049 | 83% |
  | `Resentir` | 743 | 59% |
  | `Punto clave` | 87 | **7%** |

  Perfil de tamaño del cuerpo: media 1.790 B, p50 1.825 B, p90 2.496 B, p99 3.105 B, **máx 13.520 B**.

- **Anomalías del corpus** (medidas, no estimadas — ver `scripts/build_aliases.py`):
  - **55 documentos son redirecciones puras** (cuerpo <300 caracteres que solo apunta a otro término). 52 resuelven a un slug destino; **3 no tienen destino** en el corpus: `osteomielitis`, `peladera-alopecia` (destino inexistente) y `empiema` (alias ambiguo: no hay `ABSCESO` genérico, solo variantes por órgano).
  - **30 documentos llevan `(ver: X)` en el título pero tienen cuerpo propio sustancial** — NO son redirecciones y conservan su vector.
  - Se detectaron y corrigieron **1 cadena de redirección de 2 saltos** (`exceso-de-peso` → `peso-exceso-de` → `obesidad`) y **1 auto-referencia** (`peladera-alopecia` → sí mismo, bucle infinito si se sigue ingenuamente).
  - **1 documento compuesto**: `huesos-en-general.md` (13,5 KB, 5 bloques `Resentir` y 9 secciones `Tratamientos emocionales`) concatena ~9 sub-términos, entre ellos los destinos de `osteoporosis`, `fractura` y `dislocación`.
  - **Huecos de cobertura confirmados**: `irritabilidad` y `sudoración/hiperhidrosis` no existen como término en el corpus.
  - **Total de vectores base: 1.210** (1.265 − 55 redirecciones), más los chunks del documento compuesto.
- **Repo base** `ah-grupo-fundador`: tutor adaptativo de álgebra con **Google ADK 2.x** (`LlmAgent` + `Gemini`), backend **FastAPI** (streaming NDJSON), frontend **vanilla JS+Tailwind**, memoria en **PostgreSQL** (`DatabaseSessionService` + tabla `profiles`), auth **PBKDF2 + JWT HS256**, `tutor/guardrails.py` (prompt-injection determinista), `tutor/ratelimit.py`, `tutor/audit.py`, infra **Terraform** (Cloud Run + Cloud SQL + Secret Manager). Un solo contenedor back+front.

### Decisiones clave (acordadas en sesión de requisitos)
| # | Tema | Decisión |
|---|---|---|
| D1 | Motor de vectores | **FAISS** (índice en proceso/archivo). PostgreSQL queda **solo** para memoria/auth/auditoría |
| D2 | Embeddings local | **`bge-m3`** (Ollama, multilingüe, 1024 dims) |
| D3 | LLM local | **`gemma4:latest`** vía Ollama (integrado con ADK vía LiteLlm) |
| D4 | Comportamiento | Interpretación emocional + **disclaimer médico obligatorio** + escalamiento de emergencias |
| D5 | Memoria | Sesiones ADK + **perfil con historial de consultas** |
| D6 | Auth | Igual que el repo base: email+clave (PBKDF2) + **JWT Bearer HS256** |
| D7 | Frontend | Login + chat con **fuentes/citas RAG visibles** |
| D8 | QA/Evidencia | pytest de seguridad **+ arnés completo** (chrome-devtools GIFs, métricas bootstrap, PDF LaTeX) |
| D9 | Makefile | **Solo Docker** (build/up/down/logs); el resto por scripts |
| D10 | LLM en nube | **Gemini vía Vertex AI** (recomendación por defecto; confirmación antes de migrar) |
| D11 | Recuperación | **Multi-hop**: relacionar varios síntomas cuando aplique |

## 4. Personas y casos de uso

**Personas**
- **P1. Usuario final**: persona que consulta el significado emocional de un síntoma/enfermedad.
- **P2. Operador/Dev**: levanta el sistema local o lo despliega en GCP y ejecuta tests/evidencia.

**Historias de usuario**
- **US1.** Como usuario, me **registro e inicio sesión** con email+clave y obtengo un token.
- **US2.** Como usuario, **pregunto por un síntoma** ("me duele la garganta a menudo") y el agente me devuelve su interpretación emocional citando el término del diccionario.
- **US3.** Como usuario, **describo varios síntomas** y el agente los relaciona en una lectura integrada.
- **US4.** Como usuario, **vuelvo otro día** y el agente recuerda mis consultas anteriores (memoria).
- **US5.** Como usuario, veo **de qué término** salió cada parte de la respuesta (chips de fuente).
- **US6.** Como usuario, si intento un ataque (injection) el sistema lo **bloquea**; si reporto una emergencia médica, recibe una respuesta de **escalamiento** con disclaimer.
- **US7.** Como operador, levanto todo con `make up` y regenero índice/evidencia con scripts.

## 5. Requisitos funcionales (FR)

### 5.1 Dominio y motor de conversación
- **FR-01.** El agente responde en **español**, como especialista en enfermedades emocionales.
- **FR-02.** Antes de responder, el agente **recupera del RAG** los términos relevantes (no improvisa).
- **FR-03.** La respuesta debe **citar las fuentes** (términos) usadas.
- **FR-04.** Si el usuario describe **varios síntomas**, el agente los recupera y los **relaciona** (multi-hop), sin perder claridad.
- **FR-05.** Toda respuesta incluye **disclaimer** explícito: contenido de autoconocimiento/reflexión, **no** es consejo médico; sugerir consultar profesional.

- **FR-05a. Nivel de riesgo por término.** Cada término lleva un `risk_tier` en `meta.json` (de `rag/risk_tiers.json`, generado por `scripts/build_risk_tiers.py`). **156 términos (12,3% del corpus)** están en nivel elevado:

  | Nivel | Términos | Ejemplos |
  |---|---:|---|
  | `oncologico` | 52 | `cancer-de-colon`, `adenocarcinoma-bronquioalveolar` |
  | `cardio_cerebrovascular` | 28 | `corazon-infarto-agudo-de-miocardio`, `aneurisma` |
  | `psiquiatrico` | 28 | `suicidio`, `automutilacion`, `depresion`, `anorexia` |
  | `metabolico_grave` | 16 | `sangre-diabetes`, `cerebro-epilepsia` |
  | `obstetrico` | 12 | `aborto-espontaneo`, `embarazo-eclampsia` |
  | `pediatrico` | 11 | `asma-del-bebe`, `enfermedad-en-el-nino` |
  | `infeccioso_agudo` | 9 | `cerebro-meningitis`, `bronconeumonia` |
  | `estandar` | 1.109 | el resto |

  **Cuando el término recuperado en primer lugar es de nivel elevado, la derivación médica ENCABEZA la respuesta** y la lectura emocional se ofrece después, explícitamente como *reflexión complementaria* — nunca como explicación del origen del síntoma. Un disclaimer al pie de una lectura cálida y confiada no compensa este riesgo: el daño real no es legal, es el usuario que retrasa la consulta médica.

  La frontera es **diagnóstico clínico vs. estado emocional**: `angustia`, `ansiedad`, `estrés`, `insomnio` y `burnout` quedan deliberadamente en `estandar` — son el núcleo temático del diccionario y forzar derivación en cada consulta de ansiedad haría el producto inservible.

- **FR-05b. Prohibición de lenguaje causal.** En **todos** los niveles, incluido `estandar`, se prohíben las formulaciones que atribuyen causa («esto ocurre porque…», «tu cuerpo te dice que…», «la causa emocional de tu X es…»). El registro obligatorio es **asociativo** («el diccionario relaciona X con…», «una lectura posible es…»). Verificable por patrones en `tests/test_medical_safety.py`.

- **FR-06.** Ante señales de **emergencia**, el agente **NO recupera ni interpreta emocionalmente**: responde con escalamiento a servicios de salud. La lista de disparadores es un **artefacto versionado del repo** (`rag/emergency_patterns.json`), no una frase dentro del prompt, y cada patrón tiene un caso en el arnés. Cubre como mínimo: ideación suicida, autolesión, cuadro coronario agudo, urgencia pediátrica, intoxicación/sobredosis, síntomas neurológicos súbitos.
- **FR-07.** Si el usuario pregunta algo **fuera de dominio**, el agente se reencauza cortésmente al diccionario.

### 5.2 RAG

- **FR-08.** Script de **indexado** (`python -m index`): lee `data/*.md`, extrae título/cuerpo, genera **embeddings `bge-m3`** y construye el **índice FAISS** (`data/index/diccionario.index`) + un **sidecar** `data/index/meta.json` con `faiss_id → {title, slug, letter, content, risk_tier}`.

- **FR-08a. Alias de redirección.** El indexado consume `rag/aliases.json` (generado por `scripts/build_aliases.py`). Los **55 documentos de redirección pura NO reciben vector propio**: se registran como alias del slug destino. Sin esto, una consulta por «otitis» recupera con alta similitud un documento que solo dice «consulta OREJAS – OTITIS» y el agente cita una fuente vacía — rompiendo O1/US5 en términos comunes.
  - La resolución de destinos **colapsa cadenas** (A→B→C ⇒ A→C) y **neutraliza ciclos**; ambos casos existen en el corpus.
  - La resolución **nunca usa coincidencia difusa de texto**: sobre este corpus produce `ABSCESO`→`obsesion` y `LARINGITIS`→`rinitis`. Solo coincidencia exacta o de prefijo único sobre el título normalizado; los 9 destinos restantes van en un mapa curado explícito.
  - Los 3 alias sin destino se marcan `target_slug: null` y disparan la respuesta de **sin cobertura** (FR-09b), no el stub.

- **FR-08b. Chunking.** **Un vector por documento** para 1.264 de los 1.265 términos — el perfil de tamaño (p90 2.496 B) lo hace innecesario y el corte por secciones es inviable porque la estructura no es uniforme (§3). **Excepción única**: `huesos-en-general.md` se parte por sección (~9 chunks); un solo vector para 13,5 KB de sub-términos distintos es inútil y además es el destino de 3 alias.

- **FR-09. Recuperación híbrida.** Fusión **RRF** de dos recuperadores:
  1. **Denso**: coseno sobre FAISS con embeddings `bge-m3`.
  2. **Léxico**: BM25 sobre título + cuerpo, con **match normalizado de título y alias** con peso reforzado.

  Justificación: (a) es un **diccionario** — la señal más fiable es el nombre del término («me duele la garganta» → `GARGANTA`), que un embedding no privilegia; (b) los 1.265 textos comparten vocabulario emocional casi idéntico («conflicto interno», «reprimir emociones», «miedo al cambio»), así que en el espacio denso son poco discriminables y el top-k puro es ruido plausible. Top-k configurable, **default k=5**.

- **FR-09b. Umbral y sin cobertura.** FAISS **siempre** devuelve k resultados. Si el mejor score fusionado queda por debajo de **τ**, el agente declara que **no encontró el término y NO interpreta**. Sin este piso, una consulta fuera de dominio recibe 5 términos espurios y el modelo confabula una lectura a partir de ruido — contradiciendo FR-02 («no improvisa») y FR-07. τ se fija con el gold set (§13.0), no a ojo.

- **FR-10.** El contexto recuperado se inyecta al LLM **delimitado y etiquetado** (evita que los documentos secuestren el prompt).

- **FR-10b. Presupuesto de contexto.** Máx. **800 tokens por documento** recuperado y **4.000 tokens** de contexto RAG por turno. El truncado corta por párrafo completo, nunca a media frase, y preserva siempre el título. Necesario porque k=5 sin tope puede inyectar >6k tokens en un turno.

- **FR-11.** Re-indexado **reproducible e idempotente**: regenera `.index` y `meta.json`; su reconstrucción no depende de una BD externa. `meta.json` incluye un **hash del corpus**, de modo que un índice **obsoleto** se detecte, no solo uno faltante.

### 5.3 Memoria
- **FR-12.** **Sesiones ADK** persistidas en PostgreSQL (conversación sobrevive reinicios).
- **FR-13.** **Perfil de usuario** con **historial de consultas** (síntomas/enfermedades consultados + fecha). El agente lo lee cada turno para personalizar.
- **FR-14.** Tool para **registrar consulta** y actualizar el perfil.
- **FR-14b.** `DELETE /profile/consultations`: el usuario borra su historial. Es el único dato de categoría sensible que el sistema persiste (NFR-07); poder eliminarlo es barato y demuestra la decisión de diseño. El alcance académico (§2) exime del consentimiento formal, no de esto.

### 5.4 Autenticación
- **FR-15.** `POST /api/register` y `POST /api/login` (email+clave, contraseñas PBKDF2-HMAC-SHA256).
- **FR-16.** Emisión de **token JWT (HS256)** con expiración y secreto persistido en `app_config` (o `JWT_SECRET` en cloud).
- **FR-17.** Aislamiento: `user_id` de ADK = email autenticado; cada endpoint devuelve solo datos del portador.

### 5.5 Frontend vanilla
- **FR-18.** Pantalla de **login/registro** y **chat** (sin build). **Visual ad-hoc a la temática** (calma/bienestar emocional): NO se copia el estilo visual del tutor de álgebra del repo base.
- **FR-19.** Render de **chips de fuentes** bajo cada respuesta (`basado en: VIENTRE, ANGUSTIA…`).
- **FR-20.** Nota visible de disclaimer médico en la UI del chat.

## 6. Requisitos no funcionales (NFR)

### Seguridad (crítica)
- **NFR-01.** **Anti prompt-injection** determinístico en cada mensaje antes del LLM (hereda `tutor/guardrails.py`, extendido con patrones del dominio) → bloqueo 403 + `audit_log`.
- **NFR-02.** Guardarraíles **de seguridad médica** (comportamiento FR-05/FR-06) vía instrucción de sistema + patrones de escalamiento.
- **NFR-02b.** El nivel de riesgo (FR-05a) es un **mecanismo, no una instrucción**: se resuelve en el backend a partir de `meta.json` y selecciona la plantilla de respuesta antes de que el LLM redacte. No depende de que `gemma4` obedezca el prompt. Los patrones de emergencia (FR-06) se evalúan **de forma determinista sobre el mensaje del usuario, antes de la recuperación** — igual que el guardarraíl anti-injection.
- **NFR-03.** **Anti SQL-injection**: solo consultas parametrizadas; sanitización de inputs.
- **NFR-04.** **Secretos solo por variables de entorno** (local) / Secret Manager (cloud); nunca hardcodeados ni en la imagen. Audit automático (`secrets_audit.sh`).
- **NFR-05.** **Rate-limit** por email e IP (login/register/chat).
- **NFR-06.** Cabeceras de seguridad (nosniff, DENY, HSTS en cloud). Contenedor **non-root**.
- **NFR-07.** **Clasificación del dato**: el historial de consultas (FR-13) es **categoría salud** y es el artefacto más sensible del sistema. Cifrado en reposo (Cloud SQL) y en tránsito (TLS), IAM mínimo, y **no** se loguea contenido de chats. Nota de coherencia: la regla de no-logging aplica a los chats, pero el historial se persiste por diseño — de ahí que FR-14b lo haga borrable. Al ser proyecto académico (§2) solo contiene datos propios o sintéticos.

### Rendimiento / Disponibilidad
- **NFR-08.** Streaming de respuesta (NDJSON) para UX fluida.
- **NFR-09.** Recuperación RAG < ~200 ms típica (índice FAISS cargado en memoria; HNSW/Flat).
- **NFR-10.** En GCP: escalado a cero (Cloud Run) y conexión a Cloud SQL **privada y autenticada** — por IP privada de VPC, o por **Cloud SQL Auth Proxy + IAM** si se evita el VPC Connector por costo (§12).

### Mantenibilidad
- **NFR-11.** Código plano (sin capas/DI especulativas), una sola fuente de verdad por módulo, alineado al repo base.
- **NFR-12.** `make up/down/build/logs` para Docker; scripts para index, tests, eval y evidencia.

## 7. Arquitectura

```
LOCAL (macOS)
┌──────────────────────────── Docker ------------------------------┐
│  Ollama en host: gemma4:latest (chat) + bge-m3 (embeddings)       │
│        (expuesto en host.docker.internal:11434)                   │
└───────────────────────────────────────────────────────────────────┘
         ▲  host.docker.internal:11434

Contenedor único (igual a Cloud Run en producción)
┌────────────────────────────────────────────────────────┐
│  Frontend vanilla (login + chat + chips de fuentes)     │
│    ↕ POST /chat (NDJSON + sources)                     │
│  FastAPI + ADK 2.x (LlmAgent, modelo gemma4 via LiteLlm)│
│    tools: search_dictionary / get_user_profile /         │
│           record_consultation                           │
│    guardrails (injection + médicos) + rate-limit         │
│  RAG: embedder bge-m3 + índice FAISS (coseno)               │
└────────────────────────────────────────────────────────┘
         ▲
┌────────────────────────────────────────────────────────┐
│  PostgreSQL  (servicio `db`, postgres stock)            │
│   · sesiones ADK (DatabaseSessionService)               │
│   · users / app_config / audit_log / profiles           │
└────────────────────────────────────────────────────────┘
```

**Flujo de un turno**
1. `POST /chat` con Bearer token → se valida JWT (email).
2. `check_prompt_injection` → si score alto, 403 + audit.
3. El runner ADK ejecuta el agente: el LLM decide llamar a `search_dictionary` **1..N veces** (multi-hop) y a `get_user_profile`.
4. Cada tool consulta el **índice FAISS** (vectores) y **Postgres** (perfil/sesiones) y devuelve contexto delimitado.
5. El backend observa el stream de eventos, **recoge las fuentes** usadas y las añade al payload final.
6. Streaming NDJSON al frontend; el último evento trae `text` + `sources[]`.
7. `record_consultation` actualiza el perfil; auditoría en `audit_log`.

## 8. Modelo de datos (PostgreSQL) y artefactos del RAG (FAISS)

PostgreSQL persiste **solo** auth + memoria + auditoría (Postgres stock, sin extensiones):

| Tabla | Propósito | Origen |
|---|---|---|
| `users` | email (PK), `password_hash`, `created_at` | reutilizada (`tutor/auth.py`) |
| `app_config` | `signing_secret` del JWT y configs | reutilizada |
| `audit_log` | trazas de auth/chat/bloqueos | reutilizada (`tutor/audit.py`) |
| sesiones ADK | conversación (tablas de `DatabaseSessionService`) | automáticas |
| `profiles` | `user_id` (PK), `consultations` JSONB, `updated_at` | nueva (memoria de dominio) |

- `profiles.consultations`: lista `[{symptom, term, ts}]` (historial de consultas para personalización).

El **RAG no vive en la BD**: el índice FAISS es un artefacto de archivo cargado en memoria al arrancar.

| Artefacto | Contenido | Origen |
|---|---|---|
| `data/index/diccionario.index` | vectores `bge-m3` (1024 dims) de los términos | generado por `python -m index` |
| `data/index/meta.json` | `faiss_id → {title, slug, letter, content, risk_tier}` + hash del corpus | generado por `python -m index` |
| `data/index/bm25.pkl` | índice léxico para la fusión híbrida (FR-09) | generado por `python -m index` |
| `rag/aliases.json` | 55 redirecciones → slug destino, con cadenas colapsadas | `scripts/build_aliases.py` **(hecho)** |
| `rag/risk_tiers.json` | 156 términos en 7 niveles de riesgo + política por nivel | `scripts/build_risk_tiers.py` **(hecho)** |
| `rag/emergency_patterns.json` | disparadores de escalamiento (FR-06) | curado a mano |
| `eval/gold_set.json` | 80 consultas coloquiales → slugs esperados | curado a mano **(hecho)** |

- Tamaño del índice denso: **1.210 vectores base** + ~9 chunks del documento compuesto × 1024 dims × 4 B ≈ **~5 MB**. `meta.json` con el contenido completo suma otros ~2,3 MB. Se **carga completo en memoria**; trivial de versionar, hornear en la imagen o montar desde volumen/GCS.
- Dependencia Python: `faiss-cpu` (sin GPU, suficiente para este tamaño) + `rank-bm25`.
- Los cuatro artefactos de `rag/` y `eval/` son **entradas del indexado, no salidas**: se versionan en el repo y se revisan como código.

## 9. Diseño del agente (ADK 2.x)

- **Modelo**: `LlmAgent` con `LiteLlm(model="ollama/gemma4:latest")` (local); en cloud `Gemini`/Vertex (TBD).
- **Herramientas (tools)**:
  - `search_dictionary(query: str) -> str`: recupera top-k por **fusión híbrida** (FR-09), resuelve alias (FR-08a), aplica el umbral τ (FR-09b) y devuelve `[TÍTULO] (slug, risk_tier)` + contenido recortado al presupuesto (FR-10b). Si nada supera τ, devuelve explícitamente «sin cobertura» en lugar de resultados de relleno.
  - `get_user_profile(tool_context) -> str`: historial de consultas para personalizar.
  - `record_consultation(symptoms: list[str], terms: list[str], tool_context) -> str`: persiste en `profiles`.
- **Instrucción de sistema (resumen)**:
  - Rol: especialista en **significados emocionales** de síntomas (no médico).
  - Obligatorio: recuperar con `search_dictionary` antes de responder y **citar** los términos.
  - Relacionar varios síntomas cuando el usuario los menciona.
  - **Disclaimer** en cada respuesta; **plantilla según `risk_tier`** (FR-05a) seleccionada por el backend.
  - **Registro asociativo, nunca causal** (FR-05b).
  - Si `search_dictionary` responde «sin cobertura», decirlo — **no** rellenar con interpretación.
  - Responder español, tono cálido y claro; no inventar términos fuera del diccionario.

- **Multi-hop determinista (FR-04).** El camino por defecto **no** delega la iteración al LLM: se extraen los síntomas de la consulta (una llamada con salida estructurada), se lanzan N recuperaciones **en paralelo** y se sintetiza en una sola llamada. La variante «el LLM decide llamar 1..N veces» queda como camino alternativo. Razón: con un modelo local de 9,6 GB el tool-calling iterativo es la variable menos controlable del sistema, y §14 lo reconoce como riesgo pero lo mitigaba solo con «instrucción dura», que no aplica al tool-calling. El camino determinista es testeable en `pytest` sin depender del humor del modelo.

- **Citación**: el modelo emite los slugs que **efectivamente usó** y el backend los **intersecta** con lo recuperado antes de emitir `sources[]`. Inferir las fuentes solo de las llamadas observadas reporta lo *recuperado*, no lo *usado*: si se recuperan 5 y se citan 2, la UI mostraría 5 chips — una cita falsa que erosiona justo la confianza que O1/US5 buscan construir.

## 10. API

| Endpoint | Descripción |
|---|---|
| `POST /api/register` | Crea cuenta; devuelve `{token, email, profile}` |
| `POST /api/login` | Autentica; devuelve `{token, email, profile}` |
| `POST /chat` | Streaming NDJSON (Bearer). Body `{message, session_id}`. Último evento: `{session_id, done, text, sources:[{title, slug}]}` |
| `GET /profile` | Perfil del usuario autenticado |
| `DELETE /profile/consultations` | Borra el historial de consultas del portador (FR-14b) |
| `GET /sessions` | Sesiones ADK del usuario autenticado |
| `GET /health` | Liveness |
| `/` | Frontend vanilla servido por FastAPI |

*(Los endpoints de datos van tras Bearer; superficie pública mínima: register/login/health/estático.)*

## 11. Entorno local (Docker + Makefile + Ollama)

- **Makefile** (solo Docker):
  - `make build`, `make up`, `make down`, `make logs`, `make ps`.
- **docker-compose.yml**: servicio `db` con imagen **`postgres:16-alpine`** (stock, sin extensiones) + servicio `app` (back+front) en `:8000`; el backend monta/carga el índice FAISS desde `data/index/`.
- **Requisito de host**: `ollama pull gemma4:latest` (ya está) y `ollama pull bge-m3`; backend apunta a Ollama vía `OLLAMA_BASE_URL` (local con Docker = `http://host.docker.internal:11434`; sin Docker = `http://localhost:11434`).
- **Variables de entorno** (`.env` local, nunca en imagen): `LLM_MODEL=ollama/gemma4:latest`, `EMBED_MODEL=bge-m3`, `OLLAMA_BASE_URL`, `POSTGRES_DSN`, `JWT_SECRET` (opcional), `INDEX_DIR=data/index`, `ENVIRONMENT=local`, `RATE_LIMIT_*`.
- Scripts: `scripts/index.sh` (indexar RAG → genera `data/index/`), `scripts/test.sh`, `scripts/eval.sh`, `scripts/evidence.sh`, `scripts/secrets_audit.sh`, `scripts/gifs.sh`.

## 12. Migración a GCP (recursos mínimos, IaC con Terraform)

Toda la infraestructura en la nube se define como **Infraestructura como Código (IaC) con Terraform** — no se crea nada a mano en la consola. Se reutiliza `infra/terraform/` del repo base como punto de partida y se adapta a este servicio.

| Recurso | Uso |
|---|---|
| **Cloud Run** (1 servicio, CPU, escala a 0) | contenedor único back+front (con índice FAISS cargado en memoria) |
| **Cloud SQL for PostgreSQL** (IP **privada**, stock) | auth + memoria + auditoría (el RAG **no** usa la BD) |
| **Secret Manager** | `JWT_SECRET`, credenciales DB, clave Vertex |
| **Artifact Registry** | imagen Docker |
| **Vertex AI** | **Gemini** como LLM (recomendado, TBD) |
| **GCS** (opcional) | índice FAISS + `meta.json` si no va horneado en la imagen |
| (si se requiere) **Serverless VPC Connector** | acceso privado Cloud Run → Cloud SQL |
| **(opcional)** Cloud Build | CI de la imagen |

- **Terraform `apply`/`plan`** provisiona el conjunto completo y lo mantiene reproducible: Cloud Run, Cloud SQL (IP privada, sin pgvector: queda **totalmente stock**), Secret Manager, Artifact Registry, GCS y el Serverless VPC Connector, con **IAM de mínimo privilegio** (el Cloud Run solo lee los secretos y accede a la BD).
- **Realidad de costo — «recursos mínimos» no es gratis.** Cloud Run escala a cero, pero **Cloud SQL y el Serverless VPC Connector corren 24/7 y no escalan a cero**: el piso real es ~USD 25–50/mes. Para un proyecto académico eso importa. Dos alternativas, en orden de preferencia:
  1. **Sin VPC Connector**: Cloud SQL con **Cloud SQL Auth Proxy** e IAM. Elimina el componente más caro y conserva el cifrado en tránsito. NFR-10 se ajusta: la conexión sigue siendo privada y autenticada, pero no por IP privada de VPC.
  2. **Ventana de demo**: `apply` → capturar evidencia y GIFs → `terraform destroy`. El costo baja a horas en vez de meses.

  Si el diplomado no exige despliegue vivo (§17.9), lo suficiente es **Terraform escrito y validado con `terraform plan`**: demuestra el IaC sin gastar. El objetivo O9 pide «camino claro para migrar», no un servicio corriendo.

- **Estado remoto**: el *backend* del estado de Terraform se guarda en GCS (y `tfvars`/secretos **por Secret Manager / gestión de secretos**, nunca en el repo).
- **No aplicar Terraform sin visto bueno**: hereda la política del repo base (los `*.tf` se revisan antes de `apply`).
- **Índice RAG en cloud**: dada su pequeñez (~5 MB), lo más simple es **hornearlo en la imagen** o descargarlo de **GCS** al arrancar; no se requiere servicio de vectores adicional.
- **Embeddings en nube** (pendiente de decisión, como el LLM): recomendado **Vertex text-embedding** (misma familia Gemini) para no autoalojar `bge-m3`; alternativa: correr el indexado local y subir `data/index/` a GCS.
- **LLM en nube**: se **confirmará antes del cambio** (D10); el PRD deja el switch configurable (`LLM_MODEL` → `gemini/...`).

## 13. Pruebas, evaluación y evidencia (arnés)

**13.0. Eval de recuperación (`eval/gold_set.json`) — precede a todo lo demás.**

80 consultas **en lenguaje coloquial** (como las escribe un usuario, no como aparecen en el diccionario) con sus slugs esperados, validadas contra el corpus:

| Tipo | Casos | Qué mide |
|---|---:|---|
| `single` | 31 | recuperación de un síntoma |
| `alias` | 15 | resolución de redirecciones y del documento compuesto |
| `out_of_domain` | 13 | que el umbral τ dispare «sin cobertura» |
| `risk_tier` | 10 | que la plantilla de derivación se active |
| `multi` | 6 | multi-hop con 2–3 síntomas |
| `emergency` | 5 | escalamiento sin interpretación |

Se ejecuta **sin LLM** (`python -m eval.retrieval --k 5`), así que es rápido y determinista. Sirve para **elegir k, τ y el peso de fusión con datos** antes de construir el agente, y después como criterio de aceptación.

**Metas**: `recall@5 ≥ 0,85` en `single`; `≥ 0,90` en `alias`; **`precision = 1,0` en `out_of_domain`** — un falso positivo aquí es peor que un fallo de recall, porque produce una interpretación confabulada con apariencia de fuente.

El gold set incluye deliberadamente los huecos de cobertura confirmados (`osteomielitis`, `empiema`, `irritabilidad`, `sudoración`) como casos `out_of_domain`: el sistema debe declararlos sin cobertura, no devolver el stub.

1. **pytest de seguridad** (`tests/`, sin BD real, DSN dummy): prompt-injection bloqueado, aislamiento por usuario, rate-limit, validación de token. Hereda y **extiende** `test_security.py`.
2. **pytest de seguridad médica** (`tests/test_medical_safety.py`): la plantilla de derivación se activa en los 156 términos de riesgo; ningún patrón causal (FR-05b) aparece en las respuestas; los disparadores de `rag/emergency_patterns.json` escalan sin recuperar.
3. **Evidencia de registro de usuarios y memoria**:
   - Capturas `outputs/evidence/register.png`, `profiles.png`, `sessions.png` (usuarios creados y memoria persistida vía consultas SQL/endpoints).
   - Captura `outputs/evidence/rag_sources.png` (respuesta RAG con chips de fuente).
4. **Eval de extremo a extremo** (chrome-devtools): preguntas del dominio → respuestas contra gemma4 → verificación **determinista** (que la respuesta cite/contenga el término esperado `questions.json`) → métricas (media/mediana/DE/IC95% bootstrap) → reporte LaTeX → y GIFs de escenarios.

## 14. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| `gemma4` local de calidad variable en síntesis/español | instrucción dura + fallback (cloud Gemini) + eval determinista |
| Embeddings de peor recall en español | `bge-m3` (multilingüe) + **fusión híbrida con BM25** (FR-09) + k y τ fijados con `eval/gold_set.json` |
| Baja discriminación semántica: los 1.265 textos comparten vocabulario emocional casi idéntico | la rama léxica de la fusión híbrida privilegia el nombre del término, que es la señal fiable en un diccionario |
| Stubs de redirección recuperados como fuente vacía | `rag/aliases.json`: 55 redirecciones sin vector propio, cadenas colapsadas y ciclos neutralizados (FR-08a) |
| Huecos de cobertura del corpus (`osteomielitis`, `empiema`, `irritabilidad`, `sudoración`) | umbral τ + respuesta «sin cobertura» (FR-09b); están en el gold set como casos `out_of_domain` |
| Tool-calling iterativo poco fiable en gemma4 | multi-hop **determinista** por defecto (§9): extracción de síntomas → N recuperaciones en paralelo → una síntesis |
| Ollama inaccesible desde el contenedor | `host.docker.internal` (Mac) y `OLLAMA_BASE_URL` configurable |
| Índice FAISS desincronizado con `data/*.md` | script reproducible + **hash del corpus en `meta.json`** (detecta índice obsoleto, no solo faltante) + re-indexar en el arranque |
| Arranque en frío / memoria al cargar el índice | índice compacto (~5 MB) cargado completo en RAM; se incluye en imagen o se baja de GCS |
| Responsabilidad médica: el usuario retrasa la consulta clínica tras una lectura emocional confiada | **`risk_tier` por término** (FR-05a, 156 términos): la derivación encabeza la respuesta y la lectura va como reflexión complementaria + **prohibición de lenguaje causal** (FR-05b) + escalamiento (FR-06). El disclaimer al pie es el último recurso, no la mitigación |
| Prompt-injection / jailbreak | guardrails deterministas + instrucción + rate-limit + audit |
| Fuga de datos sensibles (salud) | cifrado en reposo/tránsito, IAM mínimo, no-logging de contenido |
| Inyección vía documentos RAG | contexto delimitado/etiquetado + documentos propios |
| Costo/recursos en nube: Cloud SQL y VPC Connector **no** escalan a cero (~USD 25–50/mes) | FAISS embebido (sin servicio de vectores) + Cloud SQL Auth Proxy en vez de VPC Connector + `apply`/`destroy` acotado a la ventana de demo, o quedarse en `plan` validado (§12) |
| Alcance académico confundido con producto: sobre-ingeniería de operación | §2 lo declara explícitamente; la línea de corte de §15 prioriza evidencia sobre uptime |

## 15. Plan / Milestones

**Línea de corte explícita** (calibrada para proyecto académico, §2):

| Prioridad | Milestones | Razón |
|---|---|---|
| **Imprescindible** | M0–M5, **M7, M8** | M0–M5 es el sistema; M7 (seguridad + tests) y M8 (evidencia, eval, reporte) son **el entregable que se califica** |
| **Deseable** | M6 | Docker facilita la demo pero el sistema corre sin él |
| **Acotado** | M9 | Terraform **escrito y validado con `plan`**; `apply` solo si el diplomado exige despliegue vivo (ver §12) |

En un producto comercial el arnés de evidencia sería lo prescindible; aquí es al revés — la calificación mira el rigor del proceso, no el uptime. Lo que **sí** hay que evitar es el orden inverso: llegar al final con un PDF impecable sobre un RAG que nunca se afinó. Por eso M0 (gold set) precede a M2 y M2 no se cierra hasta alcanzar las metas de §13.0.

0. **M0 — Datos y gold set** *(hecho)*: `rag/aliases.json`, `rag/risk_tiers.json`, `eval/gold_set.json`. Pendiente: `rag/emergency_patterns.json`. Va **antes** de M2 porque es lo que permite elegir k, τ y el peso de fusión con datos en vez de intuición.
1. **M1 — Scaffold**: clonar/reusar base, renombrar paquete (`tutor` → `especialista`/`emociones`), quitar currículum de álgebra.
2. **M2 — RAG**: `index.py` (FAISS + BM25 + `meta.json` con `risk_tier` y hash), alias, chunking del documento compuesto, fusión híbrida, umbral τ, `search_dictionary`, citas intersectadas. Se cierra cuando el eval de recuperación (§13.0) alcanza las metas.
3. **M3 — Agente de dominio**: instrucción de sistema, tools, disclaimer/emergencia, multi-hop.
4. **M4 — Auth + memoria**: reutilizar auth, `profiles.consultations`, `record_consultation`.
5. **M5 — Frontend**: login/registro + chat + chips de fuentes + nota de disclaimer.
6. **M6 — Docker + Makefile**: compose (app + postgres stock) y targets Docker.
7. **M7 — Seguridad + tests**: guardrails extendidos, pytest, secrets audit.
8. **M8 — Evidencia + eval**: capturas, eval bootstrap, PDF, GIFs.
9. **M9 — GCP**: Terraform adaptado (+ Vertex LLM y embeddings, decisión previa), doc de migración.

## 16. Criterios de aceptación

- `make up` levanta app+database y el chat responde con `gemma4`.
- Registro/login devuelven token; usuarios y **memoria** persisten tras reinicio (evidencia capturada).
- **Recuperación medida contra `eval/gold_set.json` (80 casos)**: `recall@5 ≥ 0,85` en `single`, `≥ 0,90` en `alias`, `precision = 1,0` en `out_of_domain`. Las fuentes citadas son las **usadas**, no las recuperadas.
- Dos o más síntomas se **relacionan** en una respuesta (6 casos `multi` del gold set).
- **Los 156 términos de riesgo elevado encabezan con derivación médica**; ningún patrón de lenguaje causal (FR-05b) aparece en las respuestas.
- Una consulta **fuera de dominio** recibe «sin cobertura», no una interpretación de relleno.
- Toda respuesta lleva **disclaimer**; una emergencia y un intento de injection reciben la respuesta correcta (bloqueo 403 / escalamiento).
- `pytest` de seguridad **y de seguridad médica** en verde; `secrets_audit` sin hallazgos.
- Evidencia y reporte (PDF + GIFs) generados en `outputs/`.
- `make down/up` no pierde datos.

## 17. Decisiones abiertas (open questions)

1. **Nombre comercial/paquete** del agente (propongo `especialista` / proyecto `ah-emociones`). — pendiente de confirmar.
2. **LLM de producción en GCP**: Gemini vía Vertex (recomendado) vs otra opción — se decide **antes de migrar** (D10).
3. **Embeddings en nube**: Vertex text-embedding vs reutilizar `bge-m3` autoalojado — se decide **antes de migrar**. Afecta solo a cómo se genera el índice (local → GCS/hornear en imagen).
4. **Ubicación del índice FAISS en cloud**: hornear en la imagen vs descargar de GCS al arrancar (default propuesto: hornear en imagen).
5. **Modelo exacto de gemma4**: confirmar que `gemma4:latest` es estable para el eval (tamaño de contexto / latencia).
6. ~~**k y umbral** de recuperación RAG definitivos~~ — **cerrada**: dejan de ser preguntas abiertas y pasan a fijarse empíricamente en M2 con `eval/gold_set.json` (§13.0). El umbral τ es además un requisito funcional (FR-09b), no un parámetro de afinación.
7. ~~**Consentimiento de datos de salud**~~ — **cerrada por el alcance académico (§2)**: sin usuarios reales no hay obligación legal. Se conserva de todos modos el **endpoint de borrado del historial** (`DELETE /profile/consultations`) y una **nota de propósito** en el registro: cuestan poco y son justamente el tipo de decisión que el proyecto busca demostrar. Se retiran la política de retención formal y el consentimiento expreso.
8. ~~**Naturaleza del producto**~~ — **cerrada**: proyecto académico de diplomado, declarado en §2. Los guardarraíles médicos (FR-05a/b, FR-06) **se mantienen tal cual**: su corrección es parte de lo evaluado.
9. **¿El diplomado exige despliegue vivo en GCP?** Determina si M9 llega a `terraform apply` o se queda en `plan` validado. Afecta costo (§12) y no bloquea nada antes de M9. — **pendiente**.

## 18. Apéndice — qué se reutiliza del repo base

| Módulo base | Reúso |
|---|---|
| `tutor/auth.py` | tal cual (usuarios, PBKDF2, JWT HS256, `app_config`) |
| `tutor/guardrails.py` | base + patrones de dominio |
| `tutor/ratelimit.py` | tal cual |
| `tutor/audit.py` | tal cual |
| `tutor/memory.py` | sesiones ADK + tabla `profiles` (redefinida para consultas) |
| `backend/main.py` | endpoints, streaming NDJSON, cabeceras, aislamiento (+ `sources`) |
| `frontend/` | reimplementado: estética ad-hoc (bienestar emocional) + chips de fuentes |
| `Dockerfile`, `docker-compose.yml` | adaptados (Postgres stock + FAISS + Ollama) |
| `eval/`, `harness/`, `infra/terraform` | adaptados al dominio y a GCP |
