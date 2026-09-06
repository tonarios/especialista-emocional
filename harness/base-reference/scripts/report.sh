#!/usr/bin/env bash
# Compile the LaTeX metrics report to PDF with tectonic.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

if ! command -v tectonic >/dev/null 2>&1; then
  echo "tectonic not found. Install: brew install tectonic"
  exit 1
fi

exec uv run python eval/report_latex.py