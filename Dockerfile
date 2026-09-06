# Single container: FastAPI backend (especialista ADK con RAG + memoria) + frontend vanilla
# Hardened: non-root, solo copia lo necesario, NUNCA incluye .env ni secretos.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev

# Todo el contexto (el .dockerignore excluye secretos, datos, docs y artifacts)
COPY . .

RUN groupadd -r appuser && useradd -r -g appuser appuser \
    && chown -R appuser:appuser /app
USER appuser
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

# Cloud Run inyecta $PORT; en local usa 8000
CMD ["sh", "-c", "python -m uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
