# Contenedor único: FastAPI (especialista ADK con RAG + memoria) + frontend vanilla.
# Endurecido: non-root, multi-stage, sin .env ni secretos.
#
# EXTRA selecciona el perfil de dependencias (ver pyproject.toml):
#   local  -> Ollama (gemma4/bge-m3) + Postgres      [por defecto, docker compose]
#   cloud  -> Vertex + Firestore + BigQuery          [Cloud Run]
#
#   docker build --build-arg EXTRA=cloud --platform linux/amd64 -t <registry>/app:latest .
#
# Por qué multi-stage: la versión anterior hacía `chown -R appuser /app` DESPUÉS
# de crear el venv, y eso duplicaba el árbol entero en una capa de 682 MB. Aquí
# el venv se construye aparte y se copia una sola vez, ya con el dueño correcto.

# ── builder ────────────────────────────────────────────────────────────────
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

ARG EXTRA=local
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev --extra "${EXTRA}"

# ── runtime ────────────────────────────────────────────────────────────────
# python:3.12-slim en vez de la imagen de uv: el runtime no necesita uv.
FROM python:3.12-slim-bookworm

# El usuario se crea ANTES de copiar, para que todo entre ya con su dueño y no
# haga falta un `chown -R` que duplique capas.
RUN groupadd -r appuser && useradd -r -g appuser -d /app appuser

WORKDIR /app

COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv
COPY --chown=appuser:appuser especialista/ ./especialista/
COPY --chown=appuser:appuser backend/ ./backend/
COPY --chown=appuser:appuser frontend/ ./frontend/
COPY --chown=appuser:appuser rag/ ./rag/
# El índice FAISS se hornea en la imagen (§12: no hace falta servicio de
# vectores). En local, docker compose lo sobreescribe con un bind mount.
COPY --chown=appuser:appuser data/index/ ./data/index/

USER appuser
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

EXPOSE 8000

# Cloud Run inyecta $PORT; en local usa 8000.
CMD ["sh", "-c", "python -m uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
