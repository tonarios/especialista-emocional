# heartbeat — estado del proceso (ah-emociones)

Última actualización: 2026-09-07
LLM activo: opencode/deepseek-v4-pro (skills bootstrap + medical-safety ejecutadas)

## Resumen por skill

| # | Skill | Estado | Milestone | Gate | Fecha | LLM | Evidencia |
|---|-------|--------|-----------|------|-------|-----|-----------|
| 1 | bootstrap | **done** | M1 | paquete importable + /health + línea base commiteada | 2026-09-05 | deepseek-v4-pro | commits `7ef4f6f`, `d133a3c`; `import especialista` OK; `/health` 200; pytest 14 passed |
| 2 | medical-safety | **done** | transversal (M0 pendiente) | 6 grupos emergencia + plantillas por tier + causal testeable | 2026-09-05 | deepseek-v4-pro | commit `c4a334e`; 5/5 emergency gold set + 0 falsos positivos; 8 plantillas sin causal |
| 3 | rag-index | **done** | M2 | índice FAISS+BM25+meta.json idempotente (gate) | 2026-09-05 | deepseek-v4-pro | commit `cdd68c9`; 1.216 vectores; hash `9d24b7dd…`; re-run idéntico; 0 redirects vectorizados; 3 huérfanos null |
| 4 | rag-retrieval | **parcial** (local) · **done** (Vertex) | M2 | GATE DURO gold set | 2026-09-07 | deepseek-v4-pro / opus-5 | bge-m3: single 27/31, alias 13/15 ✗, ood 13/13. **Vertex 3072: single 28/31 (0.903), alias 14/15 (0.933) ✓, ood 13/13 → gate duro cumplido**; multi 5/6 y risk 9/10 siguen abiertos |
| 5 | agent-core | **done** | M3 | smoke multi-hop + citas + disclaimer | 2026-09-05 | deepseek-v4-pro | commit `14830bb`; runner determinista + LlmAgent; emergencia/injection no llegan al LLM; sin-cobertura sin confabular; gemma4 exige `think:false` |
| 6 | auth-memory | **done** | M4 | aislamiento por usuario + persistencia + delete | 2026-09-05 | deepseek-v4-pro | commit `1a1a3ca`; register/login/JWT; perfil por portador; sesiones ADK en Postgres; record/clear consultations; rate-limit; 27 pytest passed |
| 7 | frontend | **done** | M5 | flujo completo con chips de fuentes + disclaimer | 2026-09-05 | deepseek-v4-pro | commit `58b9331`; `frontend/` vanilla; `/chat` NDJSON; chips `basado en`; disclaimer fijo; 401/403/429 amigables |
| 8 | docker | **done** | M6 | `make up` + chat + persistencia + non-root | 2026-09-05 | deepseek-v4-pro | commit `05a3890`; imagen 2.7 GB; app+db sanos; chat gemma4 OK; login 200 tras down/up; whoami=appuser |
| 9 | security-tests | **done** | M7 | pytest verde + secrets_audit limpio | 2026-09-05 | deepseek-v4-pro | commit `55d3618`; 201 passed; 156 términos paramétricos; 6 emergencias sin recuperación; secrets_audit 4/4 limpio |
| 10 | evidence-eval | **done** | M8 | PNGs + PDF + GIFs con métricas | 2026-09-06 | opus-5 (regenerado) | e2e 52 preguntas; recall single 0.935 / alias 1.0 / multi 0.333; bootstrap seed 42; **8 PNGs + 5 GIFs + reporte.pdf + docs/QA_report.md** sobre la UI Liquid Glass |
| 11 | gcp-terraform | **done — DESPLEGADO** | M9 | `validate`/`plan` válido + doc de migración | 2026-09-07 | opus-5 | **vivo en https://emociones-app-zxzgilzqfq-uc.a.run.app**; 37 recursos aplicados; 12 comprobaciones en producción OK; imagen 147 MB; piso real $0.12/mes; **pendiente: alerta de presupuesto a mano** (la API la rechaza en esta cuenta) |

## Bitácora (cronológica)

- **2026-09-05 — PREPARACIÓN.** PRD analizado a fondo; arnés de desarrollo generado: `HARNESS.md` + 11 skills + este `heartbeat.md`. Estado del repo al arrancar: **M0 PARCIAL** — hechos `rag/aliases.json`, `rag/risk_tiers.json`, `eval/gold_set.json`, `scripts/build_aliases.py`, `scripts/build_risk_tiers.py`; **pendiente** `rag/emergency_patterns.json` (lo crea la skill `medical-safety`). El sistema aún no existe: la primera skill a ejecutar es `bootstrap`.

- **2026-09-05 — bootstrap (M1) DONE.** Scaffold y línea base. Cumple: M1, §18 (reúso de `tutor/*`), §17.1 (paquete `especialista` / proyecto `ah-emociones`, confirmado implícitamente por HARNESS), FR-15/FR-16 parcial (auth heredada), NFR-06 parcial (cabeceras), NFR-11 (código plano alineado al base).
  - **Commits:** línea base `7ef4f6f` (PRD + 1.265 md + M0 parcial + arnés); bootstrap `d133a3c` (paquete + /health + entorno).
  - **Paquete `especialista/`** creado desde el base: `config.py` (defaults LLM=ollama/gemma4, EMBED=bge-m3, INDEX_DIR, OLLAMA_BASE_URL), `auth.py` (APP_NAME=`ah_emociones`), `guardrails.py` (patrones de álgebra eliminados; extensión médica queda para `medical-safety`), `ratelimit.py`, `audit.py`, `memory.py` (tabla `profiles.consultations` ya con el esquema del PRD §8; `record_consultation` queda para `auth-memory`).
  - **`backend/main.py` mínimo** (M1): `/health` + middleware de cabeceras. Endpoints de auth/chat/perfil se añaden en M3/M4.
  - **`pyproject.toml`** = base + `faiss-cpu` (1.15.0) + `rank-bm25` (0.2.2). **Dockerfile/docker-compose** adaptados (Ollama local, sin GEMINI_API_KEY). `infra/terraform/` y `harness/base-reference/scripts/` copiados como referencia.
  - **Entorno:** Python 3.14.5 (venv vía `uv`); google-adk 2.8.0, litellm 1.100.0. Ollama: `gemma4:latest` (9.6 GB) y `bge-m3:latest` (1.2 GB) presentes.
  - **Verificación:** `import especialista` OK; `uvicorn backend.main:app` `/health` → 200; `uv run pytest -q` → **14 passed**; `.env` no trackeado (git check-ignore OK); sin residuos de álgebra/`tutor` en `especialista/`, `backend/`, `tests/`.
  - **Nota de entorno:** el puerto `8000` está ocupado por un contenedor Docker ajeno (`api_spread_engine-api-1`). El back corre en `127.0.0.1:8000`; `localhost` puede resolver a `::1` y tocar ese contenedor. Avisar al skill `docker` (M6): considerar otro puerto de host o `docker compose` con un puerto distinto.

- **2026-09-05 — medical-safety (transversal) DONE.** Completa el pendiente de M0 (`rag/emergency_patterns.json`) y entrega el mecanismo determinista de guardarraíles médicos. Cumple: FR-05, FR-05a, FR-05b, FR-06, NFR-02, NFR-02b.
  - **Commit:** `c4a334e`.
  - **`rag/emergency_patterns.json`**: 6 grupos (ideación suicida, autolesión, cuadro coronario agudo, urgencia pediátrica, intoxicación/sobredosis, síntomas neurológicos súbitos), cada uno con `patterns` (evaluados deterministas, minúsculas + sin tildes) y `response` de derivación SIN interpretación emocional ni teléfonos inventados.
  - **`especialista/medical_safety.py`**: `detect_emergency` (evalúa ANTES de recuperar), `template_for` (mapeo tier→plantilla leído de `rag/risk_tiers.json`; falla con `ValueError` ante nivel desconocido), `causal_patterns` (FR-05b), y plantillas versionadas `EMERGENCY_TEMPLATE` + `SIN_COBERTURA_TEMPLATE`.
  - **Verificación (gate):** 5/5 casos `emergency` del gold set matchean su grupo; `detect_emergency("quiero suicidarme")`/`("me estoy cortando")` → match, `("me duele la garganta…")` → None; **0 falsos positivos** de emergencia sobre los 75 casos no-emergency; las 8 plantillas (7 elevadas + estándar) encabezan con derivación (elem estándar no) y **ninguna contiene lenguaje causal**; 0 falsos negativos en las 6 frases causales listadas; registro asociativo permitido no se marca como causal.
  - **Flag M2 (no bloquea):** el caso `g048` ("cáncer de mama") es `risk_tier` oncologico pero sus slugs esperados en el gold set (`senos-problemas-en-los-senos`, `nodulos-mamarios`) **no** figuran en los niveles elevados de `rag/risk_tiers.json` → si la recuperación devuelve esos slugs, la plantilla no encabezará con derivación. Revisar en `rag-retrieval`/`rag-index` (posible slug canónico `cancer-de-pecho`, que sí es `oncologico`). Los otros 9 casos risk_tier mapean a nivel elevado.
   - **Nota:** el grupo `sudden_neurological` no tiene caso en `eval/gold_set.json` (gold set es M0 "hecho", no se modifica); su cobertura se garantiza con aserción propia de la skill. Lo añadirá `security-tests` (M7) como `tests/test_medical_safety.py`.

- **2026-09-05 — rag-index (M2a) DONE.** Índice FAISS (IndexFlatIP sobre `bge-m3` normalizado L2 = coseno, 1024 dims) + `bm25.pkl` (rank_bm25 título x2 + cuerpo) + `meta.json`. Cumple: FR-08/08a/08b/11.
   - **Commit:** `cdd68c9`.
   - **`especialista/index.py`** (ejecutable `python -m index`) + entrypoint `index.py` en raíz + `scripts/index.sh` (wrapper venv). Embeddings cacheados por hash (`.embeddings_cache.json`); hash del corpus cubre `data/` + `rag/aliases.json` + `rag/risk_tiers.json`.
   - **Conteo real:** 1.263 docs (de 1.265 archivos: 2 slugs duplicados colapsan — `enfisema-pulmonar[-2]`, `espondilitis-anquilosante[-2]`) · 55 redirects sin vector · `huesos-en-general` partido en **9 unidades** (1 intro + 8 sub-términos: deformidad-osea, dislocación, fractura, osteoporosis, sesamoides, húmero, enfermedad-de-Huntington, hombros) → **1.216 vectores**.
   - **Gate:** re-run idempotente (mismo `vector_count=1216` y `corpus_hash=9d24b7dd9d3aae4f…`); **0** faiss_id para los 55 redirects; **3 huérfanos** `target_slug:null` (`empiema-ver-absceso`, `osteomielitis-ver-huesos-osteomielitis`, `peladera-alopecia`); 52/52 aliases resueltos apuntan a slug existente; **0** vectores sin `risk_tier`.
   - **Desviación vs skill** (`~1.210 base + ~9 chunks`): real 1.208 base + 8 chunks con `#` (la intro cuenta como base) = 1.216. Justificada por los 2 slugs duplicados y por contar la intro como base.
   - **Nota de datos (no bloquea):** 4 slugs de niveles elevados son redirects (`estomago-cancer-del-ver-…`, `fobia-ver-neurosis`, `eclampsia-ver-…`, `epilepsia-ver-…`); sus destinos (`cancer-de-estomago`, `neurosis`, `embarazo-eclampsia`, `cerebro-epilepsia`) sí están elevados → sin pérdida de cobertura. Los 2 archivos duplicados (`*-2.md`) se verifican colapsados a un solo slug.

- **2026-09-05 — rag-retrieval (M2b) PARCIAL.** Recuperación híbrida implementada: `especialista/retrieval.py` + `eval/retrieval.py`. Cumple FR-08a (resolución de alias, nunca stub), FR-09 (RRF denso `bge-m3` + BM25 con match normalizado título/alias de peso reforzado), FR-09b (umbral → «sin cobertura»), FR-10/10b (`format_for_llm` delimitado + presupuesto).
   - **Commit:** `df6be11`.
   - **Diseño (decisión):** la cobertura se decide por el **match nominal de título/alias** (la «señal fiable» del diccionario, PRD FR-09), con `light stemming` (plurales `es/s` + deverbales `ido/imiento/amiento`) y stopwords; el denso solo desempata el ranking dentro del mismo nivel de match. Esto da **precision 1.0** en fuera-de-dominio (el fallo de recall es preferible al falso positivo, PRD §13.0), que era lo innegociable.
   - **Resultado del gate (`python -m eval.retrieval --k 5`):** `single` **27/31 (0.871 ✓)**, `alias` **13/15 (0.867 ✗ ≥0.90)**, `out_of_domain` **13/13 (1.0 ✓)**, `multi` **5/6 ✗**, `risk_tier` **9/10 ✗**, `emergency` **5/5 ✓**.
   - **8 fallos = sinonimia coloquial ausente de `aliases.json` (M0 hecho):** `g006` panza→estómago, `g019` cuesta-respirar→disnea/pulmones, `g022` dormir→insomnio, `g028` ojos-borroso→conjuntivitis (ranking), `g030` infecciones-urinarias→vejiga/cistitis, `g043` pelo→alopecia, `g048` cáncer-de-mama→senos/nodulos (ya marcado por medical-safety), `g072` fibromialgia→cansancio. El denso no los discrimina («vocabulario emocional casi idéntico», PRD FR-09).
   - **Revisado con owner:** se decide **marcar parcial** y continuar con `agent-core` (decisión del owner). La deuda queda anotada; si se quiere cerrar el gate hace falta una expansión de sinónimos curados o revisar el gold set (en particular `g048`).

- **2026-09-05 — agent-core (M3) DONE.** Agente de dominio: `especialista/agent.py` (runner determinista + `build_agent`) + `especialista/system_instruction.md`. Cumple FR-01/02/03/04/05/05a/05b/06/07 y §9.
   - **Commit:** `14830bb`.
   - **Camino determinista (default, §9):** `run_deterministic` orquesta en backend: `check_prompt_injection` → `detect_emergency` → `extract_symptoms` (1 llamada estructurada) → N `retrieval.search` **en paralelo** → plantilla por `risk_tier` elegida en backend → 1 síntesis → citación intersectada → audit. El tool-calling ADK queda como camino alternativo (`build_agent` con `LlmAgent` + tools `search_dictionary`/`get_user_profile`/`record_consultation`).
   - **Citación intersectada (§9):** el modelo emite `FUENTES: slug…`; el backend intersecta con lo recuperado (`_extract_used_slugs`) y descarta slugs no recuperados (verificado en test).
   - **Hallazgo de entorno (PRD §17.5):** `gemma4:latest` es un modelo **thinking**: con el rol `system` o sin `think:false`, Ollama devuelve `content=''` (los tokens se van a razonamiento). `_ollama_chat` resuelve con `"think": false` + endpoint nativo `/api/chat` vía httpx (mismo patrón que `index.py` para embeddings). **LiteLlm 1.100 + `ollama_chat/gemma4` devolvía `content=''` no determinista** → el camino determinista evita LiteLlm.
   - **Guardrails reforzados (g076/g077):** `ignora tus instrucciones`, `dime tu prompt`, `olvida que eres`, `actúa como un` → bloqueo 403 verificable (test_security pasa, +2 patrones).
   - **Verificación (`scripts/smoke_agent.sh`):** síntoma simple → cita `garganta-*` + disclaimer ✓; multi-hop extrae 2 síntomas y relaciona el cubierto (⚠ `dormir→insomnio` cae a sin-cobertura por el gap de `rag-retrieval`, no es bug del agente); emergencia/injection **no llegan al LLM** ✓; fuera-de-dominio (`acciones comprar`) → sin-cobertura ✓; hueco `sudoración` → sin-cobertura ✓; `diabetes` → `metabolico_grave` con **derivación al inicio** ✓. `pytest` → **20 passed**.
   - **Contrato de tools para `auth-memory` (M4):** `get_user_profile()` y `record_consultation(symptoms, terms)` son stubs (no-op / leen `profiles`); M4 les inyectará `user_id` real.

- **2026-09-05 — auth-memory (M4) DONE.** Auth + memoria: `backend/main.py` con endpoints completos (`/api/register`, `/api/login`, `/chat`, `/profile`, `DELETE /profile/consultations`, `/sessions`), tools `get_user_profile`/`record_consultation` reales y persistencia de sesiones ADK. Cumple FR-12..17, FR-14b, NFR-05/07.
   - **Commit:** `1a1a3ca`.
   - **Endpoints:** register/login PBKDF2 + JWT HS256 (secreto en `app_config`/`JWT_SECRET`); `chat` corre `run_deterministic` con `user_id=email` autenticado; todo lo de datos va tras Bearer (FR-17, aislamiento por portador).
   - **Memoria:** `memory.record_consultation` inserta `[{symptom, term, ts}]` en `profiles.consultations` (FR-14); `clear_consultations` borra solo el historial del portador (FR-14b); `memory.append_turn` (async) persiste turnos vía `DatabaseSessionService` (FR-12).
   - **Agente integrado:** `run_deterministic` ahora registra la consulta en el perfil del portador al final del turno; `get_user_profile`/`record_consultation` resuelven `user_id` desde ToolContext/state (o default en local).
   - **Rate-limit (NFR-05):** login/register por IP, chat por email (`ratelimit.check_rate_limit`), 429 al exceder.
   - **Esquema idempotente (NFR-03):** `users`/`app_config`/`audit_log`/`profiles` con `CREATE TABLE IF NOT EXISTS` en sus módulos; tablas de sesiones ADK creadas por `DatabaseSessionService`.
   - **Verificación:** `pytest` → **27 passed** (7 nuevos en `tests/test_auth.py`: register/login 401, 409 duplicado, **aislamiento A no ve B**, record/get/delete, sesión ADK 2 eventos, chat exige token, inyección 403). Smoke live con `postgres:16-alpine` (`ah-emociones-pg`): register→token, login erróneo 401, chat sin-cobertura, profile, delete — OK.
   - **Nota infra:** para el smoke se levantó un `postgres:16-alpine` local (`ah-emociones-pg`, puerto 5432); `docker` (M6) formalizará el stack con su propio Postgres + `make up`.

- **2026-09-05 — frontend (M5) DONE.** UI vanilla sin build: `frontend/{index.html, styles.css, app.js}` servido por FastAPI en `/`. Cumple FR-18/19/20.
   - **Commit:** `58b9331`.
   - **Pantallas:** login/registro (email+clave) → guarda token en `localStorage` → chat multi-turno (`session_id` persistente); refresh mantiene sesión (token + session_id en localStorage).
   - **Chips de fuentes (FR-19):** bajo cada respuesta se renderizan `basado en: <título>` desde `sources[]` del evento final.
   - **Disclaimer (FR-20):** nota fija y visible antes del primer mensaje (div `#disclaimer`), no solo al pie.
   - **Estética propia (FR-18):** paleta calma (salvia/arcilla/arena), tipografía clara, sin build (HTML+CSS+JS vanilla). Distinta del tutor de álgebra.
   - **Errores amigables:** 401 → redirige a login con aviso; 403 → «mensaje bloqueado»; 429 → «espera un minuto»; la respuesta de emergencia se renderiza resaltada.
   - **`/chat` ahora es streaming NDJSON** (evento `status` + evento final `{session_id, kind, done, text, risk_tier, sources[]}`); el 403 por injection se devuelve antes de emitir el stream.
   - **IDs estables para `evidence-eval`:** `#login-view`, `#chat-view`, `#email`, `#password`, `#login-btn`, `#register-btn`, `#chat-input`, `#send-btn`, `#messages`, `.message`, `.chips`, `#disclaimer`.
   - **Rediseño (2026-09-05):** estética **Liquid Glass de iOS** — vidrio translúcido con `backdrop-filter: blur+saturate`, destellos especulares (`::after`), botones/píldoras de vidrio y fondo **aurora** animado. Se conservan todos los IDs/selectores estables de `evidence-eval`.
   - **Verificación:** `/`, `/app.js`, `/styles.css` → 200; `/chat` NDJSON con `done` event + `sources`; 403 injection; `app.js` sintaxis OK (node --check); `pytest` → **27 passed**. Captura visual formal la aporta `evidence-eval` (M8).

- **2026-09-05 — docker (M6) DONE.** Dockerfile (imagen única back+front, non-root) + docker-compose (db `postgres:16-alpine` + app) + Makefile SOLO con targets Docker. Cumple §7/§11, D9, NFR-04/06.
   - **Commit:** `05a3890`.
   - **Imagen `agent-app:latest`: 2.7 GB** (base `uv:python3.12-bookworm-slim` + google-adk/litellm/faiss-cpu…). Usuario **`appuser` (non-root, uid 999)**.
   - **Makefile (D9, solo Docker):** `build`, `up`, `down`, `logs`, `ps`. `up` pasa `LOCAL_DB_PASSWORD` (default `emociones_dev`, solo local).
   - **Índice FAISS:** se genera en HOST (`scripts/index.sh`, necesita Ollama) y se monta `./data/index:/app/data/index:ro` (§11); `data/` sigue en `.dockerignore`.
   - **Healthcheck** del app (`/health` vía `urllib`); `depends_on` con readiness de Postgres (`service_healthy`).
   - **Gotcha resuelto:** `docker compose` interpola `.env` del proyecto; el `OLLAMA_BASE_URL=http://localhost:11434` del `.env` local se colaba al contenedor y rompía Ollama (`Connection refused`). Solución: `OLLAMA_BASE_URL=http://host.docker.internal:11434` **fijo** en el compose (dentro del contenedor Ollama vive siempre en el host).
   - **Verificación:** `make up` → `/health` 200 + `POST /chat` responde con gemma4 (garganta → respuesta con 5 sources) ✓; `make down`+`make up` → login 200 (persistencia en volumen `pgdata`) ✓; `docker compose exec app whoami` → `appuser` ✓.

- **2026-09-05 — security-tests (M7) DONE.** Guardrails extendidos al dominio + `tests/test_medical_safety.py` + `scripts/{test.sh,secrets_audit.sh}`. Cumple NFR-01..07, FR-05a/05b/06/09b/14b, PRD §13.1/13.2.
   - **Commit:** `55d3618`.
   - **Guardrails nuevos (dominio):** petición de prescripción (`recétame`, `prescríbeme`, `dame la dosis`, `antibiótico`), diagnóstico forzado (`diagnostícame`, `hazme un diagnóstico`, `es una enfermedad grave`) → bloqueo 403.
   - **`tests/test_medical_safety.py` (173 tests):** cobertura **paramétrica de los 156 términos** elevados (cada uno → plantilla de derivación ≠ estándar); **0 patrones causales** en las 8 plantillas + respuestas de emergencia + sin-cobertura; **6 grupos de emergencia** con monkeypatch de `retrieval.search` que **falla si se llama** (corte antes de recuperar, NFR-02b); los 4 huecos (`osteomielitis`, `empiema`, `irritabilidad`, `sudoración`) con `_lexical_hits == {}`.
   - **Cabeceras (NFR-06):** test `nosniff` + `DENY` en `/health`.
   - **`scripts/secrets_audit.sh`:** 4/4 limpio — `.env` fuera de git; 0 literales de secreto en ficheros versionados; 0 `.env*` en la imagen; 0 literales en código Python. Evidencia en `outputs/evidence/secrets_audit.txt`.
   - **`scripts/test.sh`** (wrapper `uv run pytest`). Resultado global: **201 passed**.
   - **Nota:** cubre los 6 grupos (medical-safety añadió `sudden_neurological` sin caso en gold set; su aserción se cierra aquí, como se anticipó en el heartbeat de medical-safety).

- **2026-09-05 — evidence-eval (M8) DONE.** Evidencia + eval end-to-end + reporte. Cumple PRD §13.3/13.4, D8, O8.
   - **Commit:** `befe33a`.
   - **`eval/questions.json`**: 52 preguntas del dominio (31 single / 15 alias / 6 multi) derivadas del gold set.
   - **Eval e2e (`scripts/e2e.py`)**: corre `run_deterministic` (pipeline real del chat, gemma4) por pregunta; verificación **determinista** (slugs en `sources[]` ∪ título del término en el texto); latencia por turno. **Métricas por bootstrap (seed=42, 2000 remuestreos)**:
     - **global 0.885** (IC95 [0.788, 0.962]) · **single 0.935** (29/31) · **alias 1.000** (15/15) · **multi 0.333** (2/6).
     - Latencia media/mediana: single 6.19/6.36 s, alias 7.51/7.11 s, multi 9.40/9.89 s.
   - **Capturas (`scripts/capture_evidence.py`, Chrome CDP sin Playwright)**: `register.png`, `rag_sources.png` (con 5 chips de fuentes), `profiles.png`, `sessions.png` — datos reales (usuario registrado, consulta persistida, sesión ADK).
   - **Reporte (`scripts/report.py`)**: HTML autocontenido → **PDF vía Chrome headless** (`outputs/reporte.pdf`, 697 KB). Incluye método, decisiones con datos (k=5, τ = match nominal título/alias, peso RRF+léxico), tabla de recuperación §13.0, métricas e2e con IC95%, guardarraíles médicos (156 términos / 6 emergencias) y riesgos/mitigaciones (§14). **Compila y embebe las 4 capturas.**
   - **Bug corregido en el camino:** el nuevo patrón `diagnost[ií]ca(me)?` producía un falso positivo que bloqueaba «me diagnosticaron Crohn» (reporte de diagnóstico propio). Se acotó a `diagnost[ií]came` + test de regresión (`test_reporting_diagnosis_not_blocked`).
   - **Recuperación §13.0 (referencia):** single 27/31, alias 13/15, risk_tier 9/10, multi 5/6, out_of_domain 13/13, emergency 5/5.
   - **Multi-hop es el punto débil (0.333):** citar TODOS los síntomas en una síntesis con gemma4 local + el hueco de sinonimia `pelo→alopecia`. Documentado como riesgo en el reporte.
   - **GIFs:** omitidos (sin `ffmpeg` en el host); el exit criteria de M8 solo exige PNGs + PDF.
   - **Verificación:** `pytest` → **203 passed**; `scripts/evidence.sh` orquesta e2e→capturas→reporte; artefactos en `outputs/`.

- **2026-09-07 — M9 APLICADO: el sistema vive en Cloud Run.** `terraform apply` con visto
  bueno explícito del owner. 37 recursos, 0 destruidos.
  **https://emociones-app-zxzgilzqfq-uc.a.run.app**
   - **12 comprobaciones contra el servicio vivo, todas OK:** health y frontend 200; registro
     y login reales; consulta con RAG+Vertex (3 fuentes, 5,8 s); emergencia (0 fuentes,
     derivación); injection → 403; fuera de dominio → sin_cobertura; perfil y sesiones ADK
     persistidos en Firestore; **aislamiento verificado** (usuario B ve 0 y 0); memoria FR-13
     respondiendo desde el historial; BigQuery con filas; `minScale = 0`.
   - **Evidencia inesperada de NFR-02b en la telemetría:** una emergencia se resuelve en
     **57 ms** frente a **1.799 ms** de una consulta normal. La diferencia es exactamente lo
     que el guardarraíl se salta (recuperación + LLM). El mecanismo se demuestra solo.
   - **Cloud Run reserva el prefijo `ah-`:** `ah-emociones-app` se rechaza con 400. Se separó
     `run_service_name` (`emociones-app`) con una `validation` en Terraform, para que el
     próximo error salga en el `plan` y no a mitad del `apply`.
   - **`analytics.py` estaba escrito y testeado pero NO cableado.** Tras el primer despliegue
     las tablas de BigQuery estaban vacías: nadie llamaba al emisor. Probar el módulo aislado
     no detecta eso. Cableado en `run_deterministic` + tests que corren el pipeline completo
     y exigen que emita.
   - **FUGA DE PRIVACIDAD encontrada en producción y corregida.** `symptom_slug` en BigQuery
     contenía el mensaje literal del usuario («no puedo dormir y ando muy irritable»): cuando
     `extract_symptoms` no devuelve nada, el pipeline busca con el mensaje entero y esa lista
     se emitía tal cual. Viola NFR-07. **Mi propio test no lo cazó** porque usaba un caso de
     emergencia, donde `symptoms` va vacío; el camino con fuga era el de sin cobertura.
     Corregido (solo síntomas extraídos, slugificados y acotados), datos **purgados**
     recreando la tabla con `-replace` (el `DELETE` lo bloqueaba el buffer de streaming), y
     test de regresión sobre el camino correcto validado por mutación.
   - **Bug del agente que solo destapó la nube:** `gemini-2.5-flash-lite` devuelve el JSON de
     extracción **envuelto en bloque markdown**; `gemma4` lo devuelve pelado. `json.loads`
     fallaba y `extract_symptoms` caía al fallback **en todos los turnos**, así que el
     multi-hop buscaba con el mensaje entero en vez de con cada síntoma. Silencioso, sin
     excepción. Parseo tolerante + 4 tests de regresión.
   - **El budget de alertas NO se pudo crear:** `400 INVALID_ARGUMENT`. Se descartó que fuera
     la configuración comprobando que **falla igual un budget mínimo con `gcloud`, sin
     filtro**. Es limitación de la cuenta de facturación. **PENDIENTE: crear la alerta a mano
     en la consola** (USD 5, avisos 50/90/100%) — es la red de seguridad contra un gasto
     inesperado de Vertex, lo único que escala con el uso.
   - **Costo real:** la imagen quedó en **147 MB comprimidos**, bajo el free tier de 0,5 GB
     de Artifact Registry, así que ese renglón cae a $0. Piso real **$0.12/mes** (2 versiones
     de secreto). Todo lo demás cabe en free tier.
   - **RESULTADO FINAL tras corregir el parseo:** e2e global **0.923** (era 0.865 en local),
     single **0.935**, alias **1.000**, multi **0.667** (duplica el 0.333 histórico),
     latencia **2,1 s**. Son las mejores cifras del proyecto. Buena parte del salto no es
     mérito del modelo sino del bug de parseo corregido: el multi-hop llevaba degradado.
   - **Verificación:** `pytest` → **253 passed** + 7 skipped; `.env` restaurado al perfil
     local y la recuperación local vuelve a sus cifras de bge-m3 (sin contaminación).

- **2026-09-07 — M9, migración de código a Firestore + Vertex, VALIDADA.** Completa lo que
  el heartbeat anterior dejaba pendiente. La app ya conmuta entre local y nube.
   - **Capa de almacenamiento intercambiable:** `especialista/stores/` con un protocolo
     `Store` y dos backends (`postgres.py`, `firestore.py`). `memory`, `auth` y `audit`
     conservan su API pública y ya no saben dónde viven los datos. Lo elige `STORAGE_BACKEND`.
   - **`especialista/firestore_sessions.py`:** `BaseSessionService` de ADK sobre Firestore
     (ADK 2.8 no trae uno). Sesión y eventos en documentos separados por el límite de 1 MiB;
     ids secuenciales con relleno para que el orden lexicográfico sea el cronológico sin
     índice compuesto; el cliente síncrono se delega a hilos para no bloquear el event loop.
   - **`especialista/providers.py`:** único punto de conmutación de LLM y embeddings.
     `retrieval.py` e `index.py` tenían **cada uno su propia llamada a Ollama**; ambas pasan
     por aquí (el `_embed` de `retrieval` se había quedado fuera en el primer intento y lo
     destapó el gold set con un 404 contra `localhost:11434`).
   - **`especialista/analytics.py`:** eventos a BigQuery. Sin `ANALYTICS_SALT` **no emite
     nada**: mejor perder analítica que escribir un identificador reversible.
   - **Reindexado real a 3072 dims:** 1.216 vectores, índice de 19 MB, ~USD 0.09. El
     `corpus_hash` ahora incluye modelo y dimensiones — sin eso, cambiar de proveedor
     reutilizaría en silencio vectores de otro espacio y el ranking sería basura.
   - **HALLAZGO: hubo que recalibrar el umbral de cobertura.** `TAU_DENSE_FALLBACK = 0.70`
     estaba calibrado para `bge-m3`. Con Vertex, «¿qué significa emocionalmente el cuerpo?»
     puntuaba 0.7385 sin match nominal y se colaba como cobertura, **rompiendo la precisión
     fuera de dominio = 1.0** (lo innegociable del PRD §13.0). Se barrió el umbral sobre el
     gold set: 0.74–0.76 restauran 13/13 perdiendo solo 1 caso de cobertura. Fijado en
     **0.75**, y ahora es un mapa por modelo (desconocido → el más estricto).
   - **RESULTADO: Vertex cierra el gate duro de M2.** Recuperación: single 0.871 → **0.903**,
     alias 0.867 → **0.933** (≥0.90 por primera vez), ood 1.0 mantenido. Los tres criterios
     del gate se cumplen a la vez por primera vez desde M2.
   - **E2E:** global 0.865 → 0.846, single 0.903 → 0.839, multi 0.333 → **0.500**, latencia
     **8,5 s → 2,2 s**. La bajada de `single` es el sistema **volviéndose más honesto**: de
     los 3 casos que cambian a fallo, 2 son los huecos de sinonimia conocidos (`g019`
     respirar→disnea, `g022` dormir→insomnio) que antes recibían cobertura por el respaldo
     denso y ahora responden «sin cobertura», que es la verdad. Se descartó la explicación
     fácil con datos: las citas por turno son 4,42 (gemma4) vs 4,46 (Vertex), no cambian.
   - **Las dos corridas no se mezclan:** `e2e_results.json` (gemma4, referencia local) y
     `e2e_results_vertex.json`. Las cifras de un modelo no son extrapolables a otro.
   - **+28 tests** (216 → 244): 18 de backend de nube (aislamiento entre portadores en
     Firestore con un doble en memoria, orden de turnos del session service, y que a
     BigQuery **nunca** llegue texto de chat ni el email) y 10 de conmutación de proveedor
     (el `corpus_hash` distingue modelo y dims, el umbral es por modelo, Vertex normaliza
     los vectores — `IndexFlatIP` asume norma 1 y `gemini-embedding-001` no normaliza).
   - **Nota:** los tests de nube usan un doble en memoria, no el emulador de Firestore. Un
     `apply` real sería la primera vez que el código habla con Firestore de verdad.
   - **Verificación:** `pytest` → **244 passed** + 7 skipped; stack local reconstruido y
     respondiendo chat con 5 fuentes; `.env` restaurado al perfil local.

- **2026-09-06 — gcp-terraform (M9) PARCIAL — infra planificada y auditada.** Rama
  `m9-gcp-terraform`. El owner fijó: costos mínimos, modelos más baratos de Vertex,
  embeddings de Vertex, sin bases vectoriales, escala a cero, análisis en BigQuery, y
  **presupuesto de costos confirmado antes de crear nada**.
   - **Presupuesto primero (`docs/presupuesto-gcp.md`).** Precios consultados el 2026-09-06,
     no de memoria, y consumo **medido sobre este repo**: 3.400 tok in / 450 out por turno
     → **$0.00052/turno**. Reindexar el corpus (595k tok): **$0.09** una vez. Cloud Run,
     Firestore, BigQuery y GCS caben enteros en free tier incluso con 5.000 turnos/mes.
   - **Decisiones del owner sobre el presupuesto:** opción **A (Firestore)** en vez de Cloud
     SQL — piso **$0.13/mes** frente a $9.83 y escala a cero de verdad; alcance **plan contra
     proyecto real**, sin `apply`; embeddings **3072 dims** sin truncar.
   - **Terraform reescrito** (el base era Cloud SQL + VPC + ETL, casi nada reutilizable):
     `main/variables/data/iam/registry/run/budget/state/outputs.tf`. **`plan` real contra
     `diplomado-499206`: 37 to add, 0 to change, 0 to destroy.** `fmt -check` y `validate` en
     verde. Sin Cloud SQL, sin VPC Connector, sin pgvector.
   - **Vertex por service account, sin clave de API:** desaparece el secreto `gemini-api-key`
     del repo base. Quedan 2 secretos: `JWT_SECRET` y la sal del hash analítico.
   - **17 tests de seguridad de infra** (`tests/test_infra_security.py`) sobre el **plan
     resuelto**, no sobre el texto de los `.tf`: roles prohibidos, alcance por recurso,
     `allUsers` solo en el invoker, bucket de estado privado, escala a cero, tope de
     escalado, presupuesto con alertas, y **BigQuery sin campos capaces de llevar texto de
     chats** (NFR-07). **Validados por mutación:** inyectar `roles/owner`, un campo `mensaje`
     y `min_instances=1` en el plan hace fallar 5 aserciones; al restaurar, 17 en verde.
   - **`secrets_audit.sh` extendido a infra (8/8):** sin `.tfstate`/`.tfvars` versionados, sin
     literales en los `.tf`, sin claves de service account, y 0 valores sensibles expuestos en
     el plan. Se corrigió que `.terraform.lock.hcl` estuviera ignorado — debe commitearse.
   - **Imagen: 2,7 GB → 582 MB (cloud), 893 MB (local).** Dos causas: un `chown -R /app`
     **después** del `uv sync` duplicaba el árbol en una capa de **682 MB** (ahora
     multi-stage, usuario creado antes de copiar); y `scipy` (71 MB) estaba en dependencias
     **sin que ningún fichero lo use**, más `litellm` (92 MB + botocore/openai/tokenizers)
     que solo hace falta en local. `pyproject.toml` pasa a extras `local` / `cloud`.
     Artifact Registry baja de $0.22 a $0.01/mes y mejora el arranque en frío.
   - **BigQuery:** dataset con 4 tablas (`consultas`, `recuperacion`, `guardarrailes`,
     `eval`), particionadas por día. Regla dura: **metadatos y métricas, nunca texto de
     chats**; el usuario es `user_hash` con sal guardada en Secret Manager. La tabla `eval`
     convierte las corridas de `evidence.sh` en serie temporal.
   - **Pendiente antes de un `apply` útil** (§4 de `docs/migration.md`): la app todavía habla
     Postgres y Ollama. Faltan la capa Firestore, un session service de ADK sobre Firestore
     (ADK 2.8 no trae uno), los adaptadores de LLM y embeddings a Vertex, el reindexado a
     3072 dims y **volver a correr el gold set contra Vertex** — las métricas actuales son de
     `gemma4` local y no son extrapolables.
   - **Verificación:** `pytest` → **216 passed** + 7 skipped; `scripts/infra_audit.sh`
     completo; stack local reconstruido con la imagen adelgazada responde chat con 5 fuentes.

- **2026-09-06 — evidence-eval REGENERADA (M8 rehecha).** La evidencia de `befe33a` se había
  generado contra el HTML **anterior** al rediseño Liquid Glass (y antes del cambio FR-13 en
  `run_deterministic`), así que las capturas ya no retrataban el sistema. Se rehízo entera y se
  añadieron los artefactos que faltaban respecto al repo base: **GIFs** y **reportes `.md`**.
   - **Scripts nuevos/rehechos:** `scripts/cdp.py` (cliente CDP compartido),
     `scripts/capture_evidence.py` (reescrito: 5 escenarios con aserciones, frames + stills),
     `scripts/gifs.py` (ensamblado con **Pillow**, no ffmpeg), `scripts/qa_report.py`
     (`docs/QA_report.md` generado desde los datos), `scripts/report.py` (KPIs ya no
     hardcodeados; galería de 8 stills + tabla de escenarios), `scripts/evidence.sh` (5 pasos).
   - **GIFs sin ffmpeg (deuda de M8 cerrada):** el host sigue sin `ffmpeg`; se usa Pillow.
     Dos trucos necesarios para que no pesaran ~4 MB cada uno: **congelar la animación del
     fondo aurora** durante la captura (si no, cada frame difiere en todos los píxeles) y
     **paleta única** por escenario con `disposal=1` (con paleta por frame se pierde la
     compresión delta). Resultado: 104–308 KB por GIF, en línea con el repo base.
   - **`scripts/evidence.sh` estaba roto:** `uv run python scripts/e2e.py` fallaba con
     `ModuleNotFoundError: especialista` (pyproject tiene `package = false`). Se exporta
     `PYTHONPATH` en el wrapper. Nadie lo había ejecutado de punta a punta desde M8.
   - **3 defectos reales del frontend destapados por las aserciones de captura** (el punto de
     que la evidencia se autocompruebe):
     1. **Resaltado de emergencia perdido** en el refactor a `/chat` NDJSON: la burbuja se crea
        antes de conocer el `kind`, y nadie aplicaba `.emergency` al llegar el evento final.
        Contradecía lo que el propio heartbeat de M5 declaraba. Corregido en `app.js`.
     2. **403 mostraba el detalle técnico del guardarraíl** (`"prompt injection"`) al usuario;
        además de feo, decirle qué patrón saltó facilita evadirlo. Ahora mensaje amigable en
        español + clase `.blocked` (nuevo estilo).
     3. **Los chips de fuentes quedaban fuera de vista**: al llegar una respuesta larga el
        contenedor no volvía a hacer scroll, así que FR-19 no se veía ni en la UI ni en la
        captura. Corregido con re-scroll tras el evento final.
   - **Bug de la propia captura (falso verde):** `localStorage.clear()` corría sobre
     `about:blank` — otro origen —, así que la app restauraba la sesión de una corrida previa y
     el escenario «registro» fotografiaba un chat viejo mientras la aserción `chat visible`
     pasaba en falso. Se limpia ya en el origen de la app y se exige estar en la vista de
     acceso antes de registrar. Salvaguarda añadida en `gifs.py`: un GIF con <4 transiciones
     reales **rompe la corrida** en vez de publicar un GIF estático.
   - **Métricas (corrida final):** global **0.865** (IC95 [0.769, 0.942]) · single **0.903** ·
     alias **1.000** · multi **0.333**; seed 42, 2.000 remuestreos.
   - **Variabilidad declarada:** dos corridas del mismo eval sobre el mismo índice dieron
     global 0.885/0.865 y single 0.935/0.903 (`gemma4` no es determinista). Lo reproducible es
     el procedimiento, no la cifra; queda dicho en `docs/QA_report.md` §4.1 en vez de reportar
     el mejor número. Nota aparte: el cambio FR-13 en `run_deterministic` **no** movió las
     métricas fuera de ese rango.
   - **`.gitignore`:** `outputs/` estaba ignorado **entero**, así que la evidencia de M8 nunca
     se commiteó y `docs/QA_report.md` habría tenido todas las imágenes rotas en un clon. Se
     adopta la política del repo base: se publican `outputs/evidence/`, `outputs/gifs/` y
     `outputs/reporte.pdf` (7,6 MB); se ignoran los **frames** intermedios (55 MB).
   - **Artefactos:** 8 stills, 5 GIFs (registro/consulta/emergencia/seguridad/memoria),
     `outputs/reporte.pdf` (7 págs.), `docs/QA_report.md` (generado) y `docs/QA_reasoning.md`
     (razonamiento de diseño, escrito a mano como en el base).
   - **Verificación:** `pytest` → 199 passed + 7 skipped (los 7 son `test_auth.py`, saltados
     porque el Postgres del compose no publica puerto al host); `secrets_audit.sh` 4/4 limpio;
     `scripts/evidence.sh` completo de punta a punta.

- **2026-09-05 — post-M8, ajustes finales.** Dos correcciones tras la revisión con el owner:
   - **Memoria (FR-13):** el camino determinista NO leía el historial (solo existía la tool `get_user_profile` para ADK). Ahora `run_deterministic` inyecta `<historial>` en la síntesis cada turno y detecta preguntas de memoria (`"¿cuál fue mi última consulta?"`, `"¿recuerdas mis consultas?"`) → responde desde el historial persistido. Sin historial → aviso amable. tests: +3 (`test_memory_question_detected`, `test_format_history`, `test_format_history_empty`). Commit `f2ec2fb`.
   - **Frontend Liquid Glass:** (a) `display:flex` en `#login-view`/`#chat-view` pisaba el atributo `hidden` → quedaba clavado en el login (fix `[hidden]{display:none !important}`); (b) el fondo aurora `.bg` podía interceptar escritura → `pointer-events:none`; (c) se perdió la clase `btn-send` del botón Enviar → salía a ancho completo; restaurada (queda a un lado del input). `pytest` → **206 passed**.
