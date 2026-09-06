---
name: auth-memory
description: Registro/login PBKDF2+JWT HS256 reutilizando los módulos base, perfiles con historial de consultas (profiles.consultations JSONB), sesiones ADK persistentes en PostgreSQL, tools get_user_profile/record_consultation y borrado del historial. FR-12..17, NFR-05.
---

# auth-memory — M4: autenticación y memoria

## Cuándo activar

- Después de `agent-core` (implementa los stubs `get_user_profile` / `record_consultation`).

## Entradas

- Módulos copiados en `bootstrap`: `especialista/auth.py`, `ratelimit.py`, `audit.py`, `memory.py` (tabla `profiles` redefinida).
- PRD §8 (modelo de datos), FR-12..17, FR-14b, NFR-05 (rate-limit email+IP), NFR-07 (clasificación del dato: historial = categoría salud, no loguear).

## Pasos

1. Endpoints en `backend/main.py`: `POST /api/register`, `POST /api/login` — PBKDF2-HMAC-SHA256; **JWT HS256 con expiración**; secret en `app_config` (o `JWT_SECRET` en cloud).
2. Redefinir `profiles`: `user_id` PK (= email autenticado), `consultations JSONB` = lista `[{symptom, term, ts}]`, `updated_at`.
3. Implementar las tools reales: `get_user_profile()` (historial del portador del turno) y `record_consultation(symptoms, terms)` — leer/escribir **solo** el perfil del portador (FR-17, aislamiento).
4. Endpoints: `GET /profile`, `DELETE /profile/consultations` (borra SOLO su historial, FR-14b), `GET /sessions` — sesiones ADK con `DatabaseSessionService` → sobreviven reinicios (FR-12).
5. Rate-limit por email e IP en login/register/chat (reusar `especialista/ratelimit.py`).
6. SQL idempotente del esquema en el repo (users, app_config, audit_log, profiles + tablas de sesiones ADK).

## Salidas

- Endpoints funcionales + tools integradas al agente + esquema SQL versionado.

## Exit criteria (M4)

- [ ] register → token; login → token; clave incorrecta → 401.
- [ ] Aislamiento: el usuario A no ve datos del usuario B (test dedicado).
- [ ] La conversación sobrevive reinicio del proceso (sesión ADK en Postgres).
- [ ] `record_consultation` inserta `[{symptom, term, ts}]`; `GET /profile` lo devuelve; `DELETE /profile/consultations` lo borra sin tocar a otro usuario.
- [ ] Rate-limit dispara 429 tras exceder el límite (email e IP).

## Verificación

```bash
pytest tests/ -k auth          # con DSN dummy donde aplique
# smoke real con postgres local (o docker M6):
curl -sX POST localhost:8000/api/register -H 'Content-Type: application/json' \
  -d '{"email":"a@t.co","password":"..."}' | jq .token
```

Registrar en heartbeat: endpoints probados y resultados del test de aislamiento.
