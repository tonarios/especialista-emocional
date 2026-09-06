---
name: bootstrap
description: Baja la línea base del repo ah-grupo-fundador al proyecto, crea el paquete especialista (tutor→especialista), elimina el currículum de álgebra, inicializa git y deja el entorno local listo (venv, .env, Ollama). Ejecutar primero, tras leer PRD.md y harness/heartbeat.md.
---

# bootstrap — M1: scaffold y línea base

## Cuándo activar

- Primer arranque del harness: no existe aún el paquete `especialista/`.
- Referencias: PRD §11, §18, M1, D3, D6; HARNESS.md (constantes).

## Entradas

- `PRD.md` (fuente de verdad).
- Repo base: `/Users/data_sci/Documents/personal/diplomado_ia/ah-grupo-fundador` — se **copia a este proyecto**; el base **no se modifica**.
- Ya existentes: `data/` (1.265 md), `rag/`, `eval/`, `scripts/` (M0 parcial).

## Pasos

1. `git init` en la raíz; crear `.gitignore` con: `.env`, `.venv/`, `__pycache__/`, `data/index/`, `outputs/`, `*.pyc`.
2. Commit de **línea base** con lo existente (PRD, data, rag, eval, scripts, harness/).
3. Copiar del repo base: `tutor/auth.py`, `tutor/guardrails.py`, `tutor/ratelimit.py`, `tutor/audit.py`, `tutor/memory.py`, `backend/main.py`, `tests/`, `requirements.txt` (o equivalente), `Dockerfile`, `docker-compose.yml`, `Makefile`, `infra/terraform/` (referencia) y `harness/` del base (referencia, nunca autoridad).
4. Renombrar paquete `tutor` → `especialista` en todo (carpetas, imports, referencias en main.py y tests). Eliminar **todo** contenido de álgebra (currículum, prompts, seeds, fixtures).
5. `requirements.txt` del proyecto = base + `faiss-cpu` + `rank-bm25`.
6. Crear `.env.example` (sin valores secretos reales) y `.env` local (fuera de git) con las variables de §11: `LLM_MODEL=ollama/gemma4:latest`, `EMBED_MODEL=bge-m3`, `OLLAMA_BASE_URL`, `POSTGRES_DSN`, `JWT_SECRET` (opcional), `INDEX_DIR=data/index`, `ENVIRONMENT=local`, `RATE_LIMIT_*`.
7. Crear venv e instalar dependencias. Verificar Ollama: `ollama list` debe mostrar `gemma4:latest` (ya está, §11); si falta `bge-m3` → `ollama pull bge-m3`.
8. `backend/main.py` mínimo: `GET /health` responda 200; sin álgebra; imports de `especialista.*` resueltos; listo para recibir los módulos de skills posteriores.

## Salidas

- Repo git con commit de línea base.
- Paquete `especialista/` importable; `requirements.txt`; `.env`/`.env.example`; `.gitignore`.
- `GET /health` → 200 (con DSN dummy; sin BD en este punto).

## Exit criteria (gate M1)

- [ ] `python -c "import especialista"` OK.
- [ ] `uvicorn backend.main:app` sirve `GET /health` → 200.
- [ ] `git log` muestra el commit de línea base; `.env` no trackeado.
- [ ] Sin residuos de álgebra ni del nombre `tutor` en `especialista/`, `backend/`, `tests/`.

## Verificación

```bash
python -c "import especialista"
curl -s localhost:8000/health
git log --oneline -1 && git status --short
grep -riE "álgebra|algebra" especialista/ backend/ tests/ | grep -viE "linear" | head
ollama list | grep -E "gemma4|bge-m3"
```

Registrar en heartbeat: commit de línea base (hash), versiones instaladas, estado de Ollama.
