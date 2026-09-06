# heartbeat — estado del proceso (ah-emociones)

Última actualización: 2026-09-05
LLM activo: opencode/deepseek-v4-pro (skill bootstrap ejecutada)

## Resumen por skill

| # | Skill | Estado | Milestone | Gate | Fecha | LLM | Evidencia |
|---|-------|--------|-----------|------|-------|-----|-----------|
| 1 | bootstrap | **done** | M1 | paquete importable + /health + línea base commiteada | 2026-09-05 | deepseek-v4-pro | commits `7ef4f6f`, `d133a3c`; `import especialista` OK; `/health` 200; pytest 14 passed |
| 2 | medical-safety | pending | transversal | — | — | — | — |
| 3 | rag-index | pending | M2 | — | — | — | — |
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
