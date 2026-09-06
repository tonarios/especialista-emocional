#!/usr/bin/env bash
# Ejecuta la batería completa de tests (pytest) del especialista.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

exec uv run pytest "$@"
