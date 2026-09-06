#!/usr/bin/env bash
# Evidencia auditable de que NINGÚN secreto entra en la imagen ni en git
# (NFR-04/06). Adaptado del base para ah-emociones.
set -euo pipefail
cd "$(dirname "$0")/.."

mkdir -p outputs/evidence
OUT=outputs/evidence/secrets_audit.txt
: > "$OUT"

log() { echo -e "$1" | tee -a "$OUT"; }

log "# Auditoría de secretos — $(date -u +%Y-%m-%dT%H:%M:%SZ)"
log ""

log "## 1. git no trackea .env (el local queda fuera del repo)"
if git check-ignore -q .env 2>/dev/null; then
  log "   ✅ PASS: .env está ignorado por git"
else
  log "   ❌ FAIL: .env no está en .gitignore"; exit 1
fi

log "## 2. Ningún fichero versionado contiene valores de secretos"
FAILS=0
# Solo literales de secreto (valor entrecomillado o esquema `postgresql://`) de
# claves conocidas; se excluyen placeholders, variables y recursos de Terraform.
while IFS= read -r f; do
  hits=$(grep -EIn \
    '(POSTGRES_DSN|POSTGRES_PASSWORD|POSTGRES_USER|JWT_SECRET|GEMINI_API_KEY|OPENAI_API_KEY|API_KEY|SECRET_KEY)[[:space:]]*[:=][[:space:]]*["'\''][^"'\''$]{8,}' \
    "$f" 2>/dev/null \
    | grep -vE 'YOUR_|EXAMPLE|example|dummy|placeholder|postgresql://test:|random_password|passwordInput|os\.environ|\$\{|_require\(' || true)
  if [ -n "$hits" ]; then
    echo "$f:" >> "$OUT"; echo "$hits" >> "$OUT"; FAILS=1
  fi
done < <(git ls-files)
if [ "$FAILS" != "0" ]; then
  log "   ❌ FAIL: hay literales de secreto versionados (ver detalle arriba)"; exit 1
fi
log "   ✅ PASS: ningún fichero versionado trae valores de secretos"

log "## 3. La imagen no contiene .env ni credenciales embebidas"
if command -v docker >/dev/null 2>&1 && docker image inspect agent-app:latest >/dev/null 2>&1; then
  FOUND=$(docker run --rm --entrypoint sh agent-app:latest \
    -c 'find /app -maxdepth 3 \( -name ".env*" -o -name "*.env" \) 2>/dev/null | wc -l' 2>/dev/null || echo "?")
  log "   ficheros .env* dentro de /app en la imagen: $FOUND (esperado 0)"
  if [ "$FOUND" != "0" ]; then log "   ❌ FAIL"; exit 1; fi
  log "   ✅ PASS"
else
  log "   ⚠ SKIP (imagen no construida; build con docker compose build)"
fi

log "## 4. No hay literales de secretos en el código Python"
HITS=$(grep -RInE '(JWT_SECRET|POSTGRES_DSN|POSTGRES_PASSWORD)\s*=\s*["'\''][^"'\'']{8,}' especialista backend 2>/dev/null || true)
if [ -n "$HITS" ]; then log "$HITS"; log "   ❌ FAIL"; exit 1; fi
log "   ✅ PASS"

log ""
log "Evidencia completa en $OUT"
rm -f /tmp/git_secrets.txt
