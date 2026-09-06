#!/usr/bin/env bash
# Scaffold a fresh tutor system from harness/templates into the repo root.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TPL="$ROOT/harness/templates"

if [ ! -d "$TPL" ]; then
  echo "No templates found at $TPL"
  exit 1
fi

echo "[scaffold] materializing templates into $ROOT ..."
cp -R "$TPL"/. "$ROOT"/

# Ensure memory DB dir exists
mkdir -p "$ROOT/data"
touch "$ROOT/data/.gitkeep"

echo "[scaffold] done. Run ./harness/scripts/bootstrap.sh to install deps."