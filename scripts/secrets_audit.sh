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

# ── Infraestructura (M9) ──────────────────────────────────────────────────

log "## 5. Terraform: sin state ni tfvars versionados"
BAD=$(git ls-files 'infra/**' | grep -E '\.tfstate|\.tfvars$|\.terraform/' || true)
if [ -n "$BAD" ]; then
  log "$BAD"; log "   ❌ FAIL: el state lleva secretos en claro y los tfvars credenciales"; exit 1
fi
for p in '*.tfvars' 'infra/terraform/.terraform/' 'infra/terraform/terraform.tfstate'; do
  git check-ignore -q "$p" 2>/dev/null || { log "   ❌ FAIL: $p no está ignorado"; exit 1; }
done
log "   ✅ PASS: sin state/tfvars en git y los patrones están ignorados"

log "## 6. Terraform: ningún secreto en claro en los .tf"
# Los valores generados salen de random_password y se guardan en Secret Manager;
# ningún `.tf` debe llevar un literal.
HITS=$(grep -RInE '(secret_data|password|api_key|token)[[:space:]]*=[[:space:]]*"[^"$]{8,}"' \
  infra/terraform --include='*.tf' 2>/dev/null \
  | grep -vE 'random_password|google_secret_manager|description|EXAMPLE|YOUR_' || true)
if [ -n "$HITS" ]; then log "$HITS"; log "   ❌ FAIL"; exit 1; fi
log "   ✅ PASS: los secretos se generan con random_password y viven en Secret Manager"

log "## 7. Terraform: no se crean claves descargables de service account"
HITS=$(grep -RIn 'google_service_account_key' infra/terraform --include='*.tf' 2>/dev/null || true)
if [ -n "$HITS" ]; then log "$HITS"; log "   ❌ FAIL: una clave descargable es un secreto que se filtra"; exit 1; fi
log "   ✅ PASS: la identidad del contenedor es el service account, sin claves"

log "## 8. El plan de Terraform no expone secretos en claro"
if [ -f outputs/evidence/tfplan.json ]; then
  # random_password.result y secret_data deben venir marcados como sensibles.
  LEAK=$(python3 - <<'PY' 2>/dev/null || echo "?"
import json
d = json.load(open("outputs/evidence/tfplan.json"))
bad = []
for c in d.get("resource_changes", []):
    sens = c["change"].get("after_sensitive") or {}
    after = c["change"].get("after") or {}
    for campo in ("secret_data", "result"):
        if campo in after and after[campo] is not None and not sens.get(campo):
            bad.append(f"{c['address']}.{campo}")
print(len(bad))
PY
)
  log "   valores sensibles expuestos en el plan: $LEAK (esperado 0)"
  if [ "$LEAK" != "0" ]; then log "   ❌ FAIL"; exit 1; fi
  log "   ✅ PASS"
else
  log "   ⚠ SKIP (sin plan; genera con scripts/infra_audit.sh)"
fi

log ""
log "Evidencia completa en $OUT"
rm -f /tmp/git_secrets.txt
