"""`BaseSessionService` de ADK respaldado por Firestore (FR-12).

ADK 2.8 trae `DatabaseSessionService`, `SqliteSessionService`,
`InMemorySessionService` y `VertexAiSessionService`, pero **ninguno de
Firestore**. Como la arquitectura de nube elegida sustituye Cloud SQL por
Firestore (docs/presupuesto-gcp.md §5), hace falta implementarlo.

Modelo de datos — la sesión y sus eventos van en documentos separados para no
chocar con el límite de 1 MiB por documento de Firestore:

    sessions/{app|user|sid}                 {app_name, user_id, session_id,
                                             state, last_update_time}
    sessions/{app|user|sid}/events/{n}      un evento, serializado por Pydantic

Los eventos usan un id secuencial con relleno (`000001`) para que el orden
lexicográfico de Firestore sea el orden cronológico: así se leen sin necesitar
un índice compuesto.

El cliente de Firestore es síncrono; los métodos de ADK son `async`. Cada
llamada bloqueante se delega a un hilo con `asyncio.to_thread` para no bloquear
el event loop de FastAPI.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any

from google.adk.events import Event
from google.adk.sessions import Session
from google.adk.sessions.base_session_service import (
    BaseSessionService,
    GetSessionConfig,
    ListSessionsResponse,
)

_SESSIONS = "sessions"
_EVENTS = "events"


def _key(app_name: str, user_id: str, session_id: str) -> str:
    """Id de documento estable. '|' no aparece en emails ni en los session_id."""
    return f"{app_name}|{user_id}|{session_id}".replace("/", "_")


class FirestoreSessionService(BaseSessionService):
    def __init__(self, client) -> None:
        self._db = client

    # ── helpers síncronos (se ejecutan en un hilo) ─────────────────
    def _doc(self, app_name: str, user_id: str, session_id: str):
        return self._db.collection(_SESSIONS).document(_key(app_name, user_id, session_id))

    def _read(self, app_name: str, user_id: str, session_id: str,
              num_recent: int | None) -> Session | None:
        ref = self._doc(app_name, user_id, session_id)
        snap = ref.get()
        if not snap.exists:
            return None
        data = snap.to_dict() or {}

        query = ref.collection(_EVENTS)
        docs = list(query.order_by("__name__").stream())
        if num_recent is not None:
            docs = docs[-num_recent:]

        events: list[Event] = []
        for d in docs:
            raw = (d.to_dict() or {}).get("event")
            if raw:
                events.append(Event.model_validate(raw))

        return Session(
            id=session_id,
            app_name=app_name,
            user_id=user_id,
            state=data.get("state") or {},
            events=events,
            last_update_time=data.get("last_update_time") or 0.0,
        )

    def _write_session(self, session: Session) -> None:
        self._doc(session.app_name, session.user_id, session.id).set(
            {
                "app_name": session.app_name,
                "user_id": session.user_id,
                "session_id": session.id,
                "state": session.state,
                "last_update_time": session.last_update_time,
            }
        )

    # ── API de ADK ─────────────────────────────────────────────────
    async def create_session(
        self,
        *,
        app_name: str,
        user_id: str,
        state: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> Session:
        sid = session_id or uuid.uuid4().hex
        session = Session(
            id=sid,
            app_name=app_name,
            user_id=user_id,
            state=state or {},
            events=[],
            last_update_time=time.time(),
        )
        await asyncio.to_thread(self._write_session, session)
        return session

    async def get_session(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
        config: GetSessionConfig | None = None,
    ) -> Session | None:
        num_recent = config.num_recent_events if config else None
        return await asyncio.to_thread(
            self._read, app_name, user_id, session_id, num_recent
        )

    async def list_sessions(
        self, *, app_name: str, user_id: str | None = None
    ) -> ListSessionsResponse:
        def _run() -> list[Session]:
            q = self._db.collection(_SESSIONS).where("app_name", "==", app_name)
            if user_id is not None:
                # Aislamiento por portador (FR-17): jamás se devuelven sesiones
                # de otro usuario.
                q = q.where("user_id", "==", user_id)
            out = []
            for snap in q.stream():
                d = snap.to_dict() or {}
                out.append(
                    Session(
                        id=d.get("session_id", snap.id),
                        app_name=d.get("app_name", app_name),
                        user_id=d.get("user_id", user_id or ""),
                        state=d.get("state") or {},
                        events=[],  # el contrato de ADK: sin eventos al listar
                        last_update_time=d.get("last_update_time") or 0.0,
                    )
                )
            # ADK las quiere de más antigua a más reciente.
            out.sort(key=lambda s: s.last_update_time)
            return out

        return ListSessionsResponse(sessions=await asyncio.to_thread(_run))

    async def delete_session(
        self, *, app_name: str, user_id: str, session_id: str
    ) -> None:
        def _run() -> None:
            ref = self._doc(app_name, user_id, session_id)
            # Los subdocumentos no se borran solos al borrar el padre.
            for d in ref.collection(_EVENTS).stream():
                d.reference.delete()
            ref.delete()

        await asyncio.to_thread(_run)

    async def append_event(self, session: Session, event: Event) -> Event:
        # La clase base actualiza el estado en memoria a partir del evento.
        event = await super().append_event(session, event)

        def _run() -> None:
            ref = self._doc(session.app_name, session.user_id, session.id)
            if not ref.get().exists:
                self._write_session(session)
            # Id secuencial con relleno: el orden lexicográfico de Firestore es
            # el cronológico, sin necesitar índice compuesto.
            n = len(list(ref.collection(_EVENTS).list_documents()))
            ref.collection(_EVENTS).document(f"{n + 1:06d}").set(
                {"event": event.model_dump(mode="json", exclude_none=True)}
            )
            ref.update({"state": session.state, "last_update_time": session.last_update_time})

        await asyncio.to_thread(_run)
        return event
