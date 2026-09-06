---
name: frontend
description: Frontend vanilla sin build: pantallas de login/registro y chat con streaming NDJSON, chips de fuentes bajo cada respuesta y nota de disclaimer visible. Estética propia de calma/bienestar (NO copiar el tutor de álgebra). FR-18/19/20.
---

# frontend — M5: UI vanilla

## Cuándo activar

- Después de `auth-memory` (usa register/login y /chat reales).

## Entradas

- API del PRD §10 (register/login; `/chat` streaming NDJSON con último evento `{session_id, done, text, sources[]}`; profile; sessions; health).
- FR-18 (estética ad-hoc de bienestar), FR-19 (chips de fuentes), FR-20 (disclaimer visible).

## Pasos

1. Pantalla de **login/registro** (email+clave) → guarda el token; redirige al chat.
2. Pantalla de **chat**: input + historial multi-turno; consume el streaming NDJSON de `POST /chat` (Bearer).
3. **Chips de fuentes** bajo cada respuesta (`basado en: VIENTRE, ANGUSTIA…`) usando `sources[]` del evento final (FR-19).
4. **Nota visible y permanente de disclaimer médico** en la UI del chat (FR-20): contenido de autoconocimiento/reflexión, no es consejo médico; sugerir consultar profesional.
5. Manejo de errores amigable: 401 (sesión vencida), 403 (injection bloqueado), 429 (rate-limit); la respuesta de emergencia se muestra normal, resaltada.
6. Estética "calma/bienestar emocional": paleta serena, tipografía legible, **sin copiar** el estilo del tutor de álgebra (FR-18). Sin build: HTML+CSS+JS vanilla (Tailwind por CDN permitido, sin compilación).
7. IDs/selectores estables en login, chat y chips (los usará `evidence-eval` para capturas y e2e).

## Salidas

- `frontend/` completo servido por FastAPI en `/`.

## Exit criteria (M5)

- [ ] Flujo manual completo: registrarse → preguntar "me duele la garganta a menudo" → respuesta con **chips de fuentes** → refresh → la sesión continúa.
- [ ] Disclaimer visible en la UI **antes** de enviar el primer mensaje.
- [ ] 401/403/429 se muestran de forma amigable (sin romper la UI).
- [ ] Estética distinta a la del repo base (inspección visual).

## Verificación

- Levantar la app (`uvicorn backend.main:app`), recorrer el flujo completo y guardar una captura temporal en `outputs/evidence/` (la evidencia formal la hace `evidence-eval`).
