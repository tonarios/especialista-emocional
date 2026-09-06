---
name: security-tests
description: Guardrails anti prompt-injection extendidos al dominio, pytest de seguridad (injection, aislamiento, rate-limit, token, SQLi) y de seguridad médica (156 términos con derivación, cero patrones causales, emergencias escalan sin recuperar), más secrets_audit sin hallazgos. M7 — imprescindible.
---

# security-tests — M7: seguridad + tests (imprescindible)

## Cuándo activar

- Con el sistema funcional (tras `frontend`; `docker` opcional). **Antes** de `evidence-eval`.

## Entradas

- `especialista/guardrails.py` (base + dominio), `especialista/medical_safety.py`, `rag/risk_tiers.json`, `rag/emergency_patterns.json`, `tests/` copiados del base.
- NFR-01..07; PRD §13 puntos 1 y 2; FR-14b.

## Pasos

1. Extender guardrails con **patrones del dominio** (asks de forzar diagnóstico/prescripción, jailbreaks típicos): `check_prompt_injection` **antes** del LLM → 403 + `audit_log` (NFR-01).
2. `tests/test_security.py` (extendido): injection bloqueado (403), **aislamiento por usuario** (dos tokens solo ven lo suyo), rate-limit (429), validación/expiración de token, intentos de SQLi no alteran consultas (solo parametrizadas, NFR-03), secretos no logueados.
3. `tests/test_medical_safety.py`:
   - Test **parametrizado** sobre los **156 términos** elevados leyendo `risk_tiers.json`: la plantilla de derivación se activa para cada uno (no muestras).
   - **Ningún patrón causal** (FR-05b) en las plantillas y respuestas de muestra.
   - Cada grupo de `rag/emergency_patterns.json` escala; monkeypatch de retrieval para **afirmar que NO se llama**.
   - Los 4 huecos confirmados (`osteomielitis`, `empiema`, `irritabilidad`, `sudoración`) → SIN COBERTURA; y `DELETE /profile/consultations` borra solo lo propio (FR-14b).
4. `scripts/secrets_audit.sh` (grep/gitleaks): `.env` fuera de git, sin claves hardcodeadas, sin `JWT_SECRET` en imagen; ejecutarlo y archivar la salida.
5. Test de cabeceras de seguridad (nosniff, DENY) en respuestas.

## Salidas

- Tests en verde + script de audit + evidencia archivada en `outputs/` (registrada en heartbeat).

## Exit criteria (M7)

- [ ] `pytest tests/` **100% verde** (sin BD real; DSN dummy donde aplique).
- [ ] `scripts/secrets_audit.sh` sin hallazgos.
- [ ] Cobertura paramétrica de los 156 términos (no muestreo).
- [ ] Los 5 grupos de emergencia con assert de no-recuperación.

## Verificación

```bash
scripts/test.sh            # pytest completo
scripts/secrets_audit.sh   # salida limpia
```

Registrar en heartbeat: número de tests, cobertura (156 términos), resultado del audit.
