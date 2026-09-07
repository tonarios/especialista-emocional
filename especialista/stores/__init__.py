"""Capa de almacenamiento intercambiable: PostgreSQL (local) o Firestore (nube).

`memory.py`, `auth.py` y `audit.py` no saben dónde viven los datos: hablan con el
`Store` que devuelve `get_store()`, elegido por `STORAGE_BACKEND`.

Por qué existe: Cloud SQL no escala a cero (~USD 9.83/mes en reposo, su instancia
más barata) y la restricción del proyecto es coste mínimo. Firestore cabe en el
free tier. Ver `docs/presupuesto-gcp.md` §5.

El backend se resuelve una sola vez y de forma perezosa: importar el paquete no
debe abrir conexiones ni exigir credenciales que quizá no hagan falta.
"""
from __future__ import annotations

from especialista.config import settings
from especialista.stores.base import Store

_store: Store | None = None


def get_store() -> Store:
    """Backend activo, instanciado una sola vez."""
    global _store
    if _store is None:
        _store = _build(settings.storage_backend)
    return _store


def _build(backend: str) -> Store:
    if backend == "firestore":
        from especialista.stores.firestore import FirestoreStore

        return FirestoreStore()
    if backend == "postgres":
        from especialista.stores.postgres import PostgresStore

        return PostgresStore()
    raise ValueError(
        f"STORAGE_BACKEND desconocido: {backend!r} (valores válidos: postgres, firestore)"
    )


def reset_store() -> None:
    """Descarta el backend cacheado. Solo para tests que cambian el entorno."""
    global _store
    _store = None


__all__ = ["Store", "get_store", "reset_store"]
