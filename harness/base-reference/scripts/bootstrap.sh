#!/usr/bin/env bash
# Install dependencies with uv and prepare .env
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv not found. Install it: https://docs.astral.sh/uv/getting-started/installation/"
  exit 1
fi

echo "[bootstrap] creating .env from template if missing ..."
if [ ! -f ".env" ]; then
  cp .env.example .env
  echo "  -> created .env (fill POSTGRES_DSN / GEMINI_API_KEY before running)"
fi

mkdir -p data
touch data/.gitkeep

echo "[bootstrap] uv sync ..."
uv sync

echo "[bootstrap] done."