"""Trazas de observabilidad: `audit_log` del store activo + log estructurado.

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

from especialista.stores import get_store

logger = logging.getLogger("especialista.audit")
logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(message)s")

def audit(
    action: str,
    *,
    user_email: str | None = None,
    client_ip: str | None = None,
    status: int | None = None,
    detail: dict | None = None,
) -> None:
    """Inserta una traza en el almacén y la emite a stdout (Cloud Logging)."""
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
        get_store().write_audit(record)
    except Exception as e:  # noqa: BLE001 — la auditoría nunca debe romper el request
        logger.info(json.dumps({"event": "audit_write_failed", "error": str(e)}))
