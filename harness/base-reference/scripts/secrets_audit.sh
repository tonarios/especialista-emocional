#!/usr/bin/env bash
# Evidencia auditable de que NINGÚN secreto entra en la imagen ni en el
# contenedor: escanea el filesystem de la imagen, el entorno del proceso y git.
set -euo pipefail
cd "$(dirname "$0")/../.."
mkdir -p outputs/evidence tmp

OUT=outputs/evidence/secrets_audit.txt
: > "$OUT"

log() { echo -e "$1" | tee -a "$OUT"; }

log "# Auditoría de secretos — $(date -u +%Y-%m-%dT%H:%M:%SZ)"
log ""

log "## 1. La imagen NO contiene .env ni credenciales embebidas"
docker build -q -t ah-gf-audit . >/dev/null
FOUND=$(docker run --rm --entrypoint sh ah-gf-audit \
  -c 'find /app -maxdepth 3 \( -name ".env*" -o -name "*.env" \) 2>/dev/null | wc -l')
log "   ficheros .env* dentro de /app en la imagen: $FOUND (esperado 0)"
if [ "$FOUND" != "0" ]; then log "   ❌ FAIL"; exit 1; fi
log "   ✅ PASS"
log ""

log "## 2. El entorno de la imagen no trae GEMINI_API_KEY/JWT_SECRET embebidos"
ENV_DUMP=$(docker run --rm --entrypoint sh ah-gf-audit -c 'env' | sort)
echo "$ENV_DUMP" >> "$OUT"
if echo "$ENV_DUMP" | grep -qE '^(GEMINI_API_KEY|JWT_SECRET|POSTGRES_DSN|POSTGRES_PASSWORD)=.+'; then
  log "   ❌ FAIL: la imagen contiene secretos embebidos"; exit 1
fi
log "   ✅ PASS"
log ""

log "## 3. La app falla al arrancar sin POSTGRES_DSN (fail-fast, sin credenciales por defecto)"
RUN_OUT=$(docker run --rm --entrypoint sh ah-gf-audit -c 'python -c "import tutor.config"' 2>&1 || true)
echo "$RUN_OUT" >> "$OUT"
if echo "$RUN_OUT" | grep -q "POSTGRES_DSN"; then
  log "   ✅ PASS: config.py exige POSTGRES_DSN y aborta sin él"
else
  log "   ❌ FAIL: no se vio el fail-fast esperado"; echo "$RUN_OUT"; exit 1
fi
log ""

log "## 4. git no contiene valores de secretos en ficheros versionados"
# Se excluyen .env.example y placeholders de documentación (YOUR_API_KEY, <...>, etc.)
: > tmp/git_secrets_real.txt
while IFS= read -r f; do
  hits=$(grep -E '(GEMINI_API_KEY|POSTGRES_DSN)=[^$[:space:]]{8,}' "$f" 2>/dev/null \
    | grep -vE 'YOUR_|<[^>]+>|placeholder' || true)
  [ -n "$hits" ] && echo "$f" >> tmp/git_secrets_real.txt
done < <(git ls-files | grep -v '.env.example')
if [ -s tmp/git_secrets_real.txt ]; then
  log "   ❌ FAIL:"; cat tmp/git_secrets_real.txt | tee -a "$OUT"; exit 1
fi
log "   ✅ PASS: ningún fichero versionado contiene valores de secretos (.env.example excluido)"
log ""

log "## 5. Inyección de secretos solo por env var del shell / Secret Manager"
log "   - local: docker-compose.yml usa \${VAR:?} del anfitrión (sin env_file; .env excluido del build)"
log "   - cloud: Cloud Run monta secretos de Secret Manager como variables de entorno (infra/terraform/cloud.tf)"
rm -rf tmp
log ""
log "Evidencia completa guardada en $OUT"
