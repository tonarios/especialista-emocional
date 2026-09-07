"""Contrato que debe cumplir cualquier backend de almacenamiento.

Son las cuatro cosas que el sistema persiste, y nada más:
  usuarios · configuración de la app · perfiles (historial) · auditoría

Las sesiones ADK NO están aquí: las gestiona un `BaseSessionService` de ADK
(`DatabaseSessionService` en Postgres, `FirestoreSessionService` en nube), que
tiene su propio contrato.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Store(Protocol):
    """Operaciones de datos, sin SQL ni Firestore a la vista."""

    name: str

    # ── Usuarios ──────────────────────────────────────────────────
    def get_user(self, email: str) -> dict | None:
        """`{email, password_hash}` o None si no existe."""
        ...

    def create_user(self, email: str, password_hash: str) -> None:
        """Alta de usuario. Lanza `ValueError` si el correo ya está registrado."""
        ...

    # ── Configuración de la app ───────────────────────────────────
    def get_config(self, key: str) -> str | None: ...

    def set_config(self, key: str, value: str) -> None: ...

    # ── Perfiles (historial de consultas, FR-14) ──────────────────
    def get_profile(self, user_id: str) -> dict | None:
        """`{user_id, consultations}` o None."""
        ...

    def upsert_profile(self, profile: dict) -> None: ...

    def list_profiles(self) -> list[dict]: ...

    # ── Auditoría ─────────────────────────────────────────────────
    def write_audit(self, record: dict) -> None:
        """Best-effort: nunca debe romper el request que la origina."""
        ...
