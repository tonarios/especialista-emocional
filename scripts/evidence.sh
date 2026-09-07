#!/usr/bin/env bash
# Evidencia M8 completa: eval e2e + capturas + GIFs + reportes (Markdown y PDF).
# Requiere: la app corriendo (`make up`), Ollama con gemma4/bge-m3, y Google Chrome.
set -euo pipefail
cd "$(dirname "$0")/.."

# El paquete `especialista` no se instala (pyproject: package = false); los
# scripts se ejecutan con la raíz del repo en el PYTHONPATH.
export PYTHONPATH="${PYTHONPATH:-}:$(pwd)"

echo "[evidence] 1/5 eval end-to-end + métricas (bootstrap seed fijo)"
uv run python scripts/e2e.py

echo "[evidence] 2/5 escenarios sobre la UI real (Chrome CDP): frames + stills"
uv run python scripts/capture_evidence.py

echo "[evidence] 3/5 GIFs animados (Pillow, sin ffmpeg)"
uv run python scripts/gifs.py

echo "[evidence] 4/5 reporte Markdown (docs/QA_report.md)"
uv run python scripts/qa_report.py

echo "[evidence] 5/5 reporte HTML -> PDF"
uv run python scripts/report.py

echo "[evidence] artefactos:"
ls -la outputs/evidence/*.png outputs/gifs/*.gif outputs/reporte.pdf docs/QA_report.md
