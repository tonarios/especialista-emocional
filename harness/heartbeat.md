# heartbeat — estado del proceso (ah-emociones)

Última actualización: 2026-09-05
LLM activo: opencode/deepseek-v4-pro (skills bootstrap + medical-safety ejecutadas)

## Resumen por skill

| # | Skill | Estado | Milestone | Gate | Fecha | LLM | Evidencia |
|---|-------|--------|-----------|------|-------|-----|-----------|
| 1 | bootstrap | **done** | M1 | paquete importable + /health + línea base commiteada | 2026-09-05 | deepseek-v4-pro | commits `7ef4f6f`, `d133a3c`; `import especialista` OK; `/health` 200; pytest 14 passed |
| 2 | medical-safety | **done** | transversal (M0 pendiente) | 6 grupos emergencia + plantillas por tier + causal testeable | 2026-09-05 | deepseek-v4-pro | commit `c4a334e`; 5/5 emergency gold set + 0 falsos positivos; 8 plantillas sin causal |
| 3 | rag-index | **done** | M2 | índice FAISS+BM25+meta.json idempotente (gate) | 2026-09-05 | deepseek-v4-pro | commit `cdd68c9`; 1.216 vectores; hash `9d24b7dd…`; re-run idéntico; 0 redirects vectorizados; 3 huérfanos null |
| 4 | rag-retrieval | **parcial** | M2 | GATE DURO gold set | 2026-09-05 | deepseek-v4-pro | single 27/31; ood 13/13; emergency 5/5; alias 13/15; multi 5/6; risk 9/10 — sinonimia coloquial ausente de aliases.json |
| 5 | agent-core | **done** | M3 | smoke multi-hop + citas + disclaimer | 2026-09-05 | deepseek-v4-pro | commit `14830bb`; runner determinista + LlmAgent; emergencia/injection no llegan al LLM; sin-cobertura sin confabular; gemma4 exige `think:false` |
| 6 | auth-memory | **done** | M4 | aislamiento por usuario + persistencia + delete | 2026-09-05 | deepseek-v4-pro | commit `1a1a3ca`; register/login/JWT; perfil por portador; sesiones ADK en Postgres; record/clear consultations; rate-limit; 27 pytest passed |
| 7 | frontend | pending | M5 | — | — | — | — |
| 8 | docker | pending | M6 | — | — | — | — |
| 9 | security-tests | pending | M7 | — | — | — | — |
| 10 | evidence-eval | pending | M8 | — | — | — | — |
| 11 | gcp-terraform | pending | M9 | — | — | — | — |

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
