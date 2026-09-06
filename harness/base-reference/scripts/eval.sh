#!/usr/bin/env bash
# Run the tutor evaluation: run prompts against the real LLM, verify deterministically,
# compute metrics (bootstrap) and compile the LaTeX report.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

echo "[eval] 1/3 running prompts against the primary LLM ..."
uv run python -m eval.run_eval

echo "[eval] 2/3 metrics (media, mediana, std, IC95 bootstrap) ..."
uv run python eval/report.py

echo "[eval] 3/3 LaTeX report (tectonic) ..."
uv run python eval/report_latex.py
echo "[eval] done."