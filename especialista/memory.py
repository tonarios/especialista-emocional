"""Memoria persistente del especialista (dominio emocional).

Dos capas, independientes del backend concreto (`especialista.stores`):
  1. Sesiones de Google ADK -> `session_service` (la conversación sobrevive
     reinicios, FR-12). Postgres: `DatabaseSessionService`. Nube:
     `FirestoreSessionService`.
  2. Perfiles de usuario -> historial de consultas (FR-14). El agente lo lee
     cada turno para personalizar (FR-13).

Este módulo no sabe si detrás hay PostgreSQL o Firestore: eso lo decide
`STORAGE_BACKEND`. Ver `docs/presupuesto-gcp.md` §5.
"""
from __future__ import annotations

import datetime

from especialista.stores import get_store

APP_NAME = "ah_emociones"

_session_service = None


def _svc():
    """Session service del backend activo, instanciado de forma perezosa."""
    global _session_service
    if _session_service is None:
        _session_service = get_store().session_service()
    return _session_service


class _SessionServiceProxy:
    """Mantiene `memory.session_service` como atributo de módulo.

    Existía antes como instancia creada al importar. Ahora se resuelve al primer
    uso, para que importar `memory` no exija credenciales del backend.
    """

    def __getattr__(self, name):
        return getattr(_svc(), name)


session_service = _SessionServiceProxy()


def _default_profile(user_id: str) -> dict:
    return {"user_id": user_id, "consultations": []}


def get_profile(user_id: str) -> dict:
    """Lee el perfil persistido de un usuario (o lo crea vacío)."""
    profile = get_store().get_profile(user_id)
    if profile is None:
        profile = _default_profile(user_id)
        get_store().upsert_profile(profile)
    return profile


def list_profiles() -> list[dict]:
    """Todos los perfiles persistidos (evidencia de memoria)."""
    return get_store().list_profiles()


def record_consultation(user_id: str, symptoms: list[str], terms: list[str]) -> dict:
    """Añade una consulta al historial del usuario (FR-14).

    La entrada sigue el esquema del PRD §8: `{symptom, term, ts}`, donde
    `symptom` y `term` son listas (una consulta puede tocar varios términos).
    """
    profile = get_profile(user_id)
    entry = {
        "symptom": list(symptoms),
        "term": list(terms),
        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    profile["consultations"].append(entry)
    get_store().upsert_profile(profile)
    return entry


def clear_consultations(user_id: str) -> dict:
    """Borra el historial del usuario, y solo el suyo (FR-14b)."""
    profile = _default_profile(user_id)
    get_store().upsert_profile(profile)
    return profile


async def append_turn(app_name: str, user_id: str, session_id: str, author: str, text: str) -> None:
    """Persiste un turno en la sesión ADK (FR-12: sobrevive reinicios)."""
    from google.adk.events import Event
    from google.genai import types as gm

    svc = _svc()
    session = await svc.get_session(
        app_name=app_name, user_id=user_id, session_id=session_id
    )
    if session is None:
        session = await svc.create_session(
            app_name=app_name, user_id=user_id, session_id=session_id
        )
    role = "user" if author == "user" else "model"
    event = Event(author=author, content=gm.Content(role=role, parts=[gm.Part(text=text)]))
    await svc.append_event(session, event)


async def list_sessions(user_id: str | None = None) -> list[dict]:
    """Sesiones ADK persistidas (evidencia de memoria conversacional).

    Con `user_id` se aíslan SOLO las de ese portador (FR-17).
    """
    svc = _svc()
    if user_id is None:
        user_ids = [p["user_id"] for p in list_profiles()] or ["user"]
    else:
        user_ids = [user_id]

    out: list[dict] = []
    for uid in user_ids:
        response = await svc.list_sessions(app_name=APP_NAME, user_id=uid)
        for s in response.sessions:
            full = await svc.get_session(app_name=APP_NAME, user_id=uid, session_id=s.id)
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
