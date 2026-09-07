"""Backend PostgreSQL — el de desarrollo local (docker compose).

Es el código que vivía repartido en `memory.py`, `auth.py` y `audit.py`, ahora
en un solo sitio y detrás del contrato `Store`. Comportamiento idéntico:
esquema idempotente (NFR-03) y SQL siempre parametrizado.
"""
from __future__ import annotations

import datetime
import json

import psycopg

from especialista.config import settings

_SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS users (
        email         TEXT PRIMARY KEY,
        password_hash TEXT NOT NULL,
        created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS app_config (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS profiles (
        user_id       TEXT PRIMARY KEY,
        consultations JSONB NOT NULL DEFAULT '[]',
        updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS audit_log (
        id         BIGSERIAL PRIMARY KEY,
        ts         TIMESTAMPTZ NOT NULL DEFAULT now(),
        user_email TEXT,
        action     TEXT NOT NULL,
        client_ip  TEXT,
        status     INTEGER,
        detail     JSONB
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_audit_user_ts ON audit_log (user_email, ts DESC)",
)


class PostgresStore:
    name = "postgres"

    def __init__(self) -> None:
        self._conn: psycopg.Connection | None = None

    def _c(self) -> psycopg.Connection:
        if self._conn is None or self._conn.closed:
            conn = psycopg.connect(settings.postgres_dsn, autocommit=True)
            for ddl in _SCHEMA:
                conn.execute(ddl)
            self._conn = conn
        return self._conn

    # ── Usuarios ──────────────────────────────────────────────────
    def get_user(self, email: str) -> dict | None:
        row = self._c().execute(
            "SELECT email, password_hash FROM users WHERE email = %s", (email,)
        ).fetchone()
        return None if row is None else {"email": row[0], "password_hash": row[1]}

    def create_user(self, email: str, password_hash: str) -> None:
        conn = self._c()
        if conn.execute("SELECT 1 FROM users WHERE email = %s", (email,)).fetchone():
            raise ValueError("El correo ya está registrado")
        conn.execute(
            "INSERT INTO users (email, password_hash) VALUES (%s, %s)",
            (email, password_hash),
        )

    # ── Configuración ─────────────────────────────────────────────
    def get_config(self, key: str) -> str | None:
        row = self._c().execute(
            "SELECT value FROM app_config WHERE key = %s", (key,)
        ).fetchone()
        return None if row is None else row[0]

    def set_config(self, key: str, value: str) -> None:
        self._c().execute(
            """INSERT INTO app_config (key, value) VALUES (%s, %s)
               ON CONFLICT (key) DO UPDATE SET value = excluded.value""",
            (key, value),
        )

    # ── Perfiles ──────────────────────────────────────────────────
    def get_profile(self, user_id: str) -> dict | None:
        row = self._c().execute(
            "SELECT consultations FROM profiles WHERE user_id = %s", (user_id,)
        ).fetchone()
        return None if row is None else {"user_id": user_id, "consultations": row[0]}

    def upsert_profile(self, profile: dict) -> None:
        self._c().execute(
            """INSERT INTO profiles (user_id, consultations) VALUES (%s, %s)
               ON CONFLICT (user_id) DO UPDATE SET
                 consultations = excluded.consultations,
                 updated_at = now()""",
            (profile["user_id"], json.dumps(profile["consultations"])),
        )

    def list_profiles(self) -> list[dict]:
        rows = self._c().execute(
            "SELECT user_id, consultations, updated_at FROM profiles"
        ).fetchall()
        return [
            {"user_id": r[0], "consultations": r[1], "updated_at": r[2].isoformat()}
            for r in rows
        ]

    # ── Auditoría ─────────────────────────────────────────────────
    def write_audit(self, record: dict) -> None:
        self._c().execute(
            """INSERT INTO audit_log (user_email, action, client_ip, status, detail)
               VALUES (%s, %s, %s, %s, %s)""",
            (
                record.get("user"),
                record["action"],
                record.get("ip"),
                record.get("status"),
                json.dumps(record.get("detail") or {}, ensure_ascii=False),
            ),
        )

    # ── Sesiones ADK ──────────────────────────────────────────────
    def session_service(self):
        """`DatabaseSessionService` de ADK sobre el mismo Postgres."""
        from google.adk.sessions import DatabaseSessionService

        dsn = settings.postgres_dsn
        # ADK usa un engine async de SQLAlchemy: hay que nombrar el dialecto.
        if dsn.startswith("postgresql://"):
            dsn = dsn.replace("postgresql://", "postgresql+psycopg://", 1)
        return DatabaseSessionService(dsn)


def _utcnow() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()
