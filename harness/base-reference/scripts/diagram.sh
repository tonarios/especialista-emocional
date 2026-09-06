#!/usr/bin/env bash
# Compile Mermaid diagrams (harness/diagrams/*.mmd) to SVG with mmdc.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

if ! command -v mmdc >/dev/null 2>&1; then
  echo "mmdc (mermaid-cli) not found. Install: npm i -g @mermaid-js/mermaid-cli"
  exit 1
fi

mkdir -p outputs/diagrams
for f in harness/diagrams/*.mmd; do
  [ -e "$f" ] || continue
  out="outputs/diagrams/$(basename "${f%.mmd}").svg"
  echo "[diagram] $f -> $out"
  mmdc -i "$f" -o "$out" -b transparent
done
echo "[diagram] done."
