#!/usr/bin/env bash
# NUKEIT: reset the repository to the minimal harness state.
# Deletes ALL generated code, data, docs and outputs (including the memory DB).
# Keeps ONLY: AGENTS.md, harness/, docs/llms-full.txt, .gitignore
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

echo "!! NUKEIT: this will delete ALL generated code, data, docs and outputs."
echo "   Keeps ONLY: AGENTS.md, harness/, docs/llms-full.txt, .gitignore"
read -r -p "Continue? [y/N] " ans
case "$ans" in
  y|Y) ;;
  *) echo "Aborted."; exit 0 ;;
esac

# Generated code
rm -rf agent.py agents tutor backend frontend eval pyproject.toml uv.lock .env .env.example Dockerfile docker-compose.yml .dockerignore README.md

# Generated docs
rm -f docs/QA_report.md docs/QA_reasoning.md docs/agent.md docs/architecture.md

# Environment & build
rm -rf .venv .uv

# Data (memory DB: ADK sessions + profiles) & outputs
rm -rf data outputs

echo "Done. Repo reset to minimal harness state."
echo "Regenerate a system with: ./harness/scripts/scaffold.sh && ./harness/scripts/bootstrap.sh"