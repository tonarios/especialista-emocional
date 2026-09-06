"""Memoria persistente del especialista (dominio emocional).

Dos capas sobre PostgreSQL:
  1. Sesiones de Google ADK -> DatabaseSessionService (conversación sobrevive reinicios).
  2. Perfiles de usuario     -> tabla `profiles` (historial de consultas).
     El agente lee este historial cada turno para personalizar.

`record_consultation` / `clear_consultations` (FR-14/14b) y el helper de
persistencia de turnos (`append_turn`) se implementan en `auth-memory` (M4).
"""
from __future__ import annotations

import datetime
import json

import psycopg
from google.adk.sessions import DatabaseSessionService

from especialista.config import settings

APP_NAME = "ah_emociones"

# ── Sesiones ADK ─────────────────────────────────────────────────
# El DSN del .env es estándar (postgresql://); ADK usa un engine async de
# SQLAlchemy, así que le añadimos el dialecto explícito de psycopg 3.
_pg_dsn = settings.postgres_dsn
if _pg_dsn.startswith("postgresql://"):
    _pg_dsn = _pg_dsn.replace("postgresql://", "postgresql+psycopg://", 1)
session_service = DatabaseSessionService(_pg_dsn)

_pool: psycopg.Connection | None = None


def _connect() -> psycopg.Connection:
    """Conexión dedicada para perfiles (autocommit, esquema idempotente)."""
    global _pool
    if _pool is None or _pool.closed:
        conn = psycopg.connect(settings.postgres_dsn, autocommit=True)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS profiles (
                user_id       TEXT PRIMARY KEY,
                consultations JSONB NOT NULL DEFAULT '[]',
                updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        _pool = conn
    return _pool


def _default_profile(user_id: str) -> dict:
    return {"user_id": user_id, "consultations": []}


def get_profile(user_id: str) -> dict:
    """Lee el perfil persistido de un usuario (o lo crea vacío)."""
    row = _connect().execute(
        "SELECT consultations FROM profiles WHERE user_id = %s", (user_id,)
    ).fetchone()
    if row is None:
        profile = _default_profile(user_id)
        _upsert_profile(profile)
        return profile
    return {"user_id": user_id, "consultations": row[0]}


def _upsert_profile(profile: dict) -> None:
    """Inserta o actualiza un perfil completo en la BD."""
    _connect().execute(
        """INSERT INTO profiles (user_id, consultations)
           VALUES (%s, %s)
           ON CONFLICT(user_id) DO UPDATE SET
             consultations = excluded.consultations,
             updated_at = now()""",
        (profile["user_id"], json.dumps(profile["consultations"])),
    )


def list_profiles() -> list[dict]:
    """Todos los perfiles persistidos (para la evidencia de memoria)."""
    rows = _connect().execute(
        "SELECT user_id, consultations, updated_at FROM profiles"
    ).fetchall()
    return [
        {
            "user_id": r[0],
            "consultations": r[1],
            "updated_at": r[2].isoformat(),
        }
        for r in rows
    ]


def record_consultation(user_id: str, symptoms: list[str], terms: list[str]) -> dict:
    """Añade una consulta al historial del usuario (FR-14).

    La entrada se guarda como `{symptom, term, ts}` (esquema del PRD §8);
    `symptom` y `term` son listas (la consulta puede tocar varios términos).
    """
    profile = get_profile(user_id)
    entry = {
        "symptom": list(symptoms),
        "term": list(terms),
        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    profile["consultations"].append(entry)
    _upsert_profile(profile)
    return entry


def clear_consultations(user_id: str) -> dict:
    """Borra el historial del usuario (FR-14b)."""
    profile = _default_profile(user_id)
    _upsert_profile(profile)
    return profile


async def append_turn(app_name: str, user_id: str, session_id: str, author: str, text: str) -> None:
    """Persiste un turno en la sesión ADK (FR-12: sobrevive reinicios)."""
    from google.adk.events import Event
    from google.genai import types as gm

    session = await session_service.get_session(
        app_name=app_name, user_id=user_id, session_id=session_id
    )
    if session is None:
        session = await session_service.create_session(
            app_name=app_name, user_id=user_id, session_id=session_id
        )
    role = "user" if author == "user" else "model"
    event = Event(author=author, content=gm.Content(role=role, parts=[gm.Part(text=text)]))
    await session_service.append_event(session, event)


async def list_sessions(user_id: str | None = None) -> list[dict]:
    """Lista de sesiones ADK persistidas (evidencia de memoria conversacional).

    Es async porque `DatabaseSessionService.list_sessions/get_session` son asíncronos.
    Si se pasa `user_id`, se aíslan SOLO las sesiones de ese usuario (auth).
    """
    if user_id is None:
        user_ids = [p["user_id"] for p in list_profiles()] or ["user"]
    else:
        user_ids = [user_id]
    out: list[dict] = []
    for uid in user_ids:
        response = await session_service.list_sessions(app_name=APP_NAME, user_id=uid)
        for s in response.sessions:
            full = await session_service.get_session(app_name=APP_NAME, user_id=uid, session_id=s.id)
            out.append(
                {
                    "session_id": s.id,
                    "user_id": s.user_id,
                    "app_name": s.app_name,
                    "events": len(full.events) if full else 0,
                    "state": {k: v for k, v in s.state.items() if not k.startswith("temp")},
                }
            )
    return out
