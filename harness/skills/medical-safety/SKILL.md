---
name: medical-safety
description: Artefactos de seguridad médica: rag/emergency_patterns.json (pendiente de M0), plantillas de respuesta por risk_tier con derivación encabezada, registro asociativo anti-causal (FR-05b) y módulo determinista de detección. Se ejecuta antes del agente porque agent-core y security-tests la consumen.
---

# medical-safety — guardarraíles médicos (FR-05/05a/05b/06, NFR-02/02b)

## Cuándo activar

- Después de `bootstrap`, antes de `agent-core`.
- También si cambia `rag/risk_tiers.json` o se ajustan disparadores de emergencia.

## Entradas

- `rag/risk_tiers.json` (HECHO: 156 términos en 7 niveles elevados + `estandar`).
- `eval/gold_set.json` (10 casos `risk_tier` y 5 `emergency` = criterio de aceptación).
- PRD FR-05a (derivación ENCABEZA en niveles elevados; lectura como "reflexión complementaria"), FR-05b (prohibición de lenguaje causal), FR-06 (emergencia: NO recuperar ni interpretar), NFR-02b (mecanismo determinista, no instrucción de prompt).

## Pasos

1. Crear `rag/emergency_patterns.json` (artefacto versionado, curado a mano). Mínimo 6 grupos, cada uno `{id, patterns: [regex...], response}`:
   - ideación suicida, autolesión, cuadro coronario agudo, urgencia pediátrica, intoxicación/sobredosis, síntomas neurológicos súbitos.
   - La respuesta de cada grupo **no interpreta emocionalmente**: deriva a servicios de salud de emergencia (sin inventar teléfonos; usar genéricos locales según país).
2. Crear `especialista/medical_safety.py` **determinista**:
   - `detect_emergency(text: str) -> dict | None` — evalúa los patrones **antes** de cualquier recuperación (FR-06, NFR-02b).
   - `template_for(risk_tier: str) -> str` — plantilla por nivel: para los 7 elevados (`oncologico`, `cardio_cerebrovascular`, `psiquiatrico`, `metabolico_grave`, `obstetrico`, `pediatrico`, `infeccioso_agudo`) la **derivación médica encabeza** y la lectura emocional va después, explícitamente como *reflexión complementaria*; para `estandar`, disclaimer al pie.
   - `causal_patterns(text: str) -> list[str]` — devuelve patrones causales prohibidos encontrados (lo usan los tests).
   - Plantillas versionadas: `SIN_COBERTURA_TEMPLATE` (FR-09b) y `EMERGENCY_TEMPLATE` (FR-06).
3. Fijar la lista verificable de **patrones causales prohibidos** (FR-05b), mínimo:
   - `esto ocurre porque`, `tu cuerpo te dice`, `la causa emocional de tu`, `es causado por`, `te está diciendo que`, `significa que tu (órgano) (verbo)`.
   - Registro obligatorio **asociativo**: "el diccionario relaciona X con…", "una lectura posible es…", "en clave emocional puede leerse como…".
4. Declarar el contrato con `rag/risk_tiers.json`: `template_for` debe cubrir los 8 niveles (7 + estandar) y fallar explícitamente ante nivel desconocido.

## Salidas

- `rag/emergency_patterns.json` (6+ grupos, cada patrón con caso de prueba asociado).
- `especialista/medical_safety.py` (detect/template/causal + plantillas versionadas).

## Exit criteria (gate)

- [ ] JSON válido; al menos los 5 casos `emergency` del gold set matchean un grupo.
- [ ] Los 10 casos `risk_tier` del gold set mapean a un término elevado y `template_for(nivel)` encabeza con derivación.
- [ ] `detect_emergency("quiero suicidarme")` y `detect_emergency("me estoy cortando")` → match; `detect_emergency("me duele la garganta a menudo")` → `None`.
- [ ] Los patrones causales de la lista son detectables determinísticamente (0 falsos negativos sobre las frases listadas).
- [ ] Ninguna plantilla propia contiene lenguaje causal (autoevaluación con `causal_patterns`).

## Verificación

```bash
python - <<'PY'
import json; json.load(open('rag/emergency_patterns.json'))
from especialista.medical_safety import detect_emergency, template_for, causal_patterns
assert detect_emergency("quiero suicidarme") is not None
assert detect_emergency("me duele la garganta a menudo") is None
for tier in ["oncologico","cardio_cerebrovascular","psiquiatrico","metabolico_grave","obstetrico","pediatrico","infeccioso_agudo","estandar"]:
    t = template_for(tier); assert t and not causal_patterns(t), (tier, t)
PY
```

Registrar en heartbeat: grupos creados, cobertura de los 15 casos del gold set (risk+emergency).
