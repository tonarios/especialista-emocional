"""Backend Firestore — el de Cloud Run.

Colecciones (una por entidad; los ids son naturales, no autogenerados):

    users/{email}          {password_hash, created_at}
    app_config/{key}       {value}
    profiles/{user_id}     {consultations: [...], updated_at}
    audit_log/{auto}       {ts, user_email, action, client_ip, status, detail}

Se eligió Firestore sobre Cloud SQL porque escala a cero: Cloud SQL cuesta
~USD 9.83/mes aunque nadie use el sistema. Ver `docs/presupuesto-gcp.md` §5.

Nota sobre ids: el email se usa como id de documento. Firestore prohíbe `/` en
los ids y los emails no lo llevan, pero se normaliza igual por si acaso.
"""
from __future__ import annotations

import datetime

from especialista.config import settings

_MAX_AUDIT_DETAIL = 4096  # recorte defensivo: la auditoría no es un log de payloads


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _doc_id(value: str) -> str:
    """Id de documento seguro. Firestore no admite '/' ni ids vacíos."""
    safe = value.strip().lower().replace("/", "_")
    if not safe:
        raise ValueError("id de documento vacío")
    return safe


class FirestoreStore:
    name = "firestore"

    def __init__(self, client=None) -> None:
        if client is not None:
            self._db = client
            return
        from google.cloud import firestore

        kwargs = {"project": settings.gcp_project} if settings.gcp_project else {}
        if settings.firestore_database and settings.firestore_database != "(default)":
            kwargs["database"] = settings.firestore_database
        self._db = firestore.Client(**kwargs)

    # ── Usuarios ──────────────────────────────────────────────────
    def get_user(self, email: str) -> dict | None:
        snap = self._db.collection("users").document(_doc_id(email)).get()
        if not snap.exists:
            return None
        return {"email": email, "password_hash": snap.get("password_hash")}

    def create_user(self, email: str, password_hash: str) -> None:
        ref = self._db.collection("users").document(_doc_id(email))
        try:
            # create() falla si el documento ya existe: es atómico, a diferencia
            # de un get() seguido de set(), que tiene carrera entre dos altas
            # simultáneas del mismo correo.
            ref.create({"password_hash": password_hash, "created_at": _utcnow()})
        except Exception as e:  # google.api_core.exceptions.AlreadyExists
            if type(e).__name__ == "AlreadyExists":
                raise ValueError("El correo ya está registrado") from e
            raise

    # ── Configuración ─────────────────────────────────────────────
    def get_config(self, key: str) -> str | None:
        snap = self._db.collection("app_config").document(_doc_id(key)).get()
        return snap.get("value") if snap.exists else None

    def set_config(self, key: str, value: str) -> None:
        self._db.collection("app_config").document(_doc_id(key)).set({"value": value})

    # ── Perfiles ──────────────────────────────────────────────────
    def get_profile(self, user_id: str) -> dict | None:
        snap = self._db.collection("profiles").document(_doc_id(user_id)).get()
        if not snap.exists:
            return None
        return {"user_id": user_id, "consultations": snap.get("consultations") or []}

    def upsert_profile(self, profile: dict) -> None:
        self._db.collection("profiles").document(_doc_id(profile["user_id"])).set(
            {"consultations": profile["consultations"], "updated_at": _utcnow()}
        )

    def list_profiles(self) -> list[dict]:
        out = []
        for snap in self._db.collection("profiles").stream():
            data = snap.to_dict() or {}
            updated = data.get("updated_at")
            out.append(
                {
                    "user_id": snap.id,
                    "consultations": data.get("consultations") or [],
                    "updated_at": updated.isoformat() if hasattr(updated, "isoformat") else str(updated),
                }
            )
        return out

    # ── Auditoría ─────────────────────────────────────────────────
    def write_audit(self, record: dict) -> None:
        detail = record.get("detail") or {}
        # La auditoría registra QUÉ pasó, no el contenido del chat (NFR-07).
        if len(str(detail)) > _MAX_AUDIT_DETAIL:
            detail = {"truncado": True}
        self._db.collection("audit_log").add(
            {
                "ts": _utcnow(),
                "user_email": record.get("user"),
                "action": record["action"],
                "client_ip": record.get("ip"),
                "status": record.get("status"),
                "detail": detail,
            }
        )

    # ── Sesiones ADK ──────────────────────────────────────────────
    def session_service(self):
        from especialista.firestore_sessions import FirestoreSessionService

        return FirestoreSessionService(self._db)
