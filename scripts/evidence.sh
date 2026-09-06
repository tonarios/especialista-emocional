#!/usr/bin/env bash
# Evidencia M8: eval e2e + métricas + capturas + reporte PDF.
# Requiere: la app corriendo (make up) y Chrome para capturas/PDF.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "[evidence] 1/3 eval end-to-end + métricas (bootstrap seed fijo)"
uv run python scripts/e2e.py

echo "[evidence] 2/3 capturas vía Chrome CDP"
uv run python scripts/capture_evidence.py

echo "[evidence] 3/3 reporte HTML -> PDF"
python3 scripts/report.py

echo "[evidence] artefactos:"
ls -la outputs/evidence/*.png outputs/reporte.html outputs/reporte.pdf
