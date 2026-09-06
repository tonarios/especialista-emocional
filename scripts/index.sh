#!/usr/bin/env bash
# Indexado del RAG: regenera data/index/{diccionario.index, meta.json, bm25.pkl}.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [ ! -f .env ]; then
  echo "[index] no existe .env; copiando desde .env.example" >&2
  cp .env.example .env
fi

# La URL de Ollama por defecto apunta a localhost; en Docker se usa
# host.docker.internal. Aquí (host) basta con localhost.
exec uv run python -m index "$@"
