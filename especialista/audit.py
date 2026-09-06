"""Trazas de observabilidad en PostgreSQL: tabla audit_log + log estructurado.

Registra (best-effort, nunca rompe el flujo del request):
  - login/register (éxito y fallo)
  - turnos de chat bloqueados por prompt injection
  - respuestas 429 de rate limit
  - lecturas de perfil/sesiones
Cada evento también sale a stdout en JSON para Cloud Logging.
"""
from __future__ import annotations

import json
import logging
import sys
import time

import psycopg

from especialista.config import settings

logger = logging.getLogger("especialista.audit")
logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(message)s")

AUDIT_TABLE = """
CREATE TABLE IF NOT EXISTS audit_log (
    id         BIGSERIAL PRIMARY KEY,
    ts         TIMESTAMPTZ NOT NULL DEFAULT now(),
    user_email TEXT,
    action     TEXT NOT NULL,
    client_ip  TEXT,
    status     INTEGER,
    detail     JSONB
)
"""
AUDIT_INDEX = "CREATE INDEX IF NOT EXISTS idx_audit_user_ts ON audit_log (user_email, ts DESC)"

_conn: psycopg.Connection | None = None


def _connect() -> psycopg.Connection:
    global _conn
    if _conn is None or _conn.closed:
        conn = psycopg.connect(settings.postgres_dsn, autocommit=True)
        conn.execute(AUDIT_TABLE)
        conn.execute(AUDIT_INDEX)
        _conn = conn
    return _conn


def audit(
    action: str,
    *,
    user_email: str | None = None,
    client_ip: str | None = None,
    status: int | None = None,
    detail: dict | None = None,
) -> None:
    """Inserta una traza en audit_log y la emite a stdout (Cloud Logging)."""
    record = {
        "event": "audit",
        "action": action,
        "user": user_email,
        "ip": client_ip,
        "status": status,
        "detail": detail or {},
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    logger.info(json.dumps(record, ensure_ascii=False))
    try:
        _connect().execute(
            """INSERT INTO audit_log (user_email, action, client_ip, status, detail)
               VALUES (%s, %s, %s, %s, %s)""",
            (user_email, action, client_ip, status, json.dumps(detail or {}, ensure_ascii=False)),
        )
    except Exception as e:  # noqa: BLE001 — la auditoría nunca debe romper el request
        logger.info(json.dumps({"event": "audit_write_failed", "error": str(e)}))
