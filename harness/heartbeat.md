# heartbeat — estado del proceso (ah-emociones)

Última actualización: 2026-09-05
LLM activo: opencode/deepseek-v4-pro (skills bootstrap + medical-safety ejecutadas)

## Resumen por skill

| # | Skill | Estado | Milestone | Gate | Fecha | LLM | Evidencia |
|---|-------|--------|-----------|------|-------|-----|-----------|
| 1 | bootstrap | **done** | M1 | paquete importable + /health + línea base commiteada | 2026-09-05 | deepseek-v4-pro | commits `7ef4f6f`, `d133a3c`; `import especialista` OK; `/health` 200; pytest 14 passed |
| 2 | medical-safety | **done** | transversal (M0 pendiente) | 6 grupos emergencia + plantillas por tier + causal testeable | 2026-09-05 | deepseek-v4-pro | commit `c4a334e`; 5/5 emergency gold set + 0 falsos positivos; 8 plantillas sin causal |
| 3 | rag-index | **done** | M2 | índice FAISS+BM25+meta.json idempotente (gate) | 2026-09-05 | deepseek-v4-pro | commit `cdd68c9`; 1.216 vectores; hash `9d24b7dd…`; re-run idéntico; 0 redirects vectorizados; 3 huérfanos null |
| 4 | rag-retrieval | pending | M2 | GATE DURO gold set | — | — | — |
| 5 | agent-core | pending | M3 | — | — | — | — |
| 6 | auth-memory | pending | M4 | — | — | — | — |
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
