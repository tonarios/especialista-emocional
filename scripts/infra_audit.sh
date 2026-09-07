#!/usr/bin/env bash
# Auditoría de seguridad de la infraestructura GCP (M9).
#
# Genera el `terraform plan` REAL contra el proyecto y verifica sobre él las
# propiedades de seguridad. Se audita el plan resuelto, no los .tf como texto:
# un comentario no engaña a un plan.
#
# Requiere: terraform, gcloud autenticado (application-default login).
# Produce:  outputs/evidence/tfplan.json, tfplan.txt, infra_audit.txt
set -euo pipefail
cd "$(dirname "$0")/.."

TF=infra/terraform
OUT=outputs/evidence
mkdir -p "$OUT"

PROJECT="${TF_VAR_project_id:-$(gcloud config get-value project 2>/dev/null)}"
BILLING="${TF_VAR_billing_account:-$(gcloud billing projects describe "$PROJECT" \
  --format='value(billingAccountName)' 2>/dev/null | sed 's|billingAccounts/||')}"
IMAGE="${TF_VAR_image:-us-central1-docker.pkg.dev/$PROJECT/ah-emociones/app:latest}"

echo "[infra-audit] proyecto: $PROJECT"

echo "[infra-audit] 1/5 formato"
terraform -chdir="$TF" fmt -check -recursive

echo "[infra-audit] 2/5 validate"
terraform -chdir="$TF" init -backend=false -input=false >/dev/null
terraform -chdir="$TF" validate

echo "[infra-audit] 3/5 plan contra el proyecto real (no crea nada)"
terraform -chdir="$TF" plan -input=false \
  -var="project_id=$PROJECT" \
  -var="billing_account=$BILLING" \
  -var="image=$IMAGE" \
  -out=/tmp/ah.tfplan >/dev/null
terraform -chdir="$TF" show -json /tmp/ah.tfplan > "$OUT/tfplan.json"
terraform -chdir="$TF" show -no-color /tmp/ah.tfplan > "$OUT/tfplan.txt"

# El ID de la cuenta de facturación no es una credencial, pero es un
# identificador interno y esta evidencia se commitea en un repo público.
if [ -n "$BILLING" ]; then
  for f in "$OUT/tfplan.json" "$OUT/tfplan.txt"; do
    python3 - "$f" "$BILLING" <<'PY'
import sys, pathlib
f, billing = pathlib.Path(sys.argv[1]), sys.argv[2]
f.write_text(f.read_text().replace(billing, "REDACTED-BILLING-ACCOUNT"))
PY
  done
fi

echo "[infra-audit] 4/5 aserciones de seguridad sobre el plan"
uv run pytest tests/test_infra_security.py -q --no-header \
  | tee "$OUT/infra_audit.txt"

echo "[infra-audit] 5/5 auditoría de secretos (incluye infra/)"
scripts/secrets_audit.sh >/dev/null

{
  echo ""
  echo "# Resumen — $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "proyecto:  $PROJECT"
  echo "recursos:  $(python3 -c "
import json;d=json.load(open('$OUT/tfplan.json'))
print(len(d['planned_values']['root_module']['resources']))")"
  echo "cambios:   $(grep -oE '[0-9]+ to add, [0-9]+ to change, [0-9]+ to destroy' "$OUT/tfplan.txt" | tail -1)"
} >> "$OUT/infra_audit.txt"

echo "[infra-audit] evidencia en $OUT/{tfplan.json,tfplan.txt,infra_audit.txt,secrets_audit.txt}"
