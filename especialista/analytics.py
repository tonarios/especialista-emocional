"""Emisión de eventos analíticos a BigQuery.

**Regla dura (NFR-07 + FR-05b): aquí NUNCA entra el texto de una conversación.**
Son datos de salud. A BigQuery van métricas y metadatos: qué términos se
citaron, qué nivel de riesgo se aplicó, cuánto tardó y qué guardarraíl disparó.

El usuario se identifica con `user_hash` = HMAC-SHA256(sal, email) truncado. La
sal vive en Secret Manager, así que el hash no se revierte por fuerza bruta
sobre el espacio de correos conocidos. **Sin sal no se emite nada**: es
preferible perder analítica a escribir un identificador reversible.

Todo es best-effort y no bloqueante: si BigQuery falla, el chat sigue.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import threading

from especialista.config import settings

logger = logging.getLogger("especialista.analytics")

_client = None
_client_lock = threading.Lock()


def enabled() -> bool:
    """Solo con dataset configurado Y sal disponible."""
    return bool(settings.bq_dataset and settings.analytics_salt)


def user_hash(email: str) -> str:
    """Seudónimo estable del usuario. Nunca el email."""
    if not settings.analytics_salt:
        raise RuntimeError("ANALYTICS_SALT ausente: no se puede seudonimizar")
    mac = hmac.new(
        settings.analytics_salt.encode("utf-8"),
        (email or "").strip().lower().encode("utf-8"),
        hashlib.sha256,
    )
    return mac.hexdigest()[:32]


def text_hash(text: str) -> str:
    """Hash de una consulta, para agrupar repeticiones sin guardar el texto."""
    return hashlib.sha256((text or "").strip().lower().encode("utf-8")).hexdigest()[:32]


def _bq():
    global _client
    with _client_lock:
        if _client is None:
            from google.cloud import bigquery

            _client = bigquery.Client(project=settings.gcp_project or None)
        return _client


def _insert(table: str, row: dict) -> None:
    errors = _bq().insert_rows_json(f"{settings.bq_dataset}.{table}", [row])
    if errors:
        logger.info(json.dumps({"event": "bq_insert_failed", "table": table, "errors": str(errors)[:500]}))


def emit(table: str, row: dict) -> None:
    """Envía una fila en segundo plano. Nunca bloquea ni rompe el request."""
    if not enabled():
        return

    def _run() -> None:
        try:
            _insert(table, row)
        except Exception as e:  # noqa: BLE001 — la analítica jamás rompe el chat
            logger.info(json.dumps({"event": "bq_emit_failed", "error": str(e)[:300]}))

    threading.Thread(target=_run, daemon=True).start()


# ── Eventos del dominio ───────────────────────────────────────────

def consulta(
    *,
    email: str,
    session_id: str | None,
    symptoms: list[str],
    terms: list[str],
    risk_tier: str | None,
    kind: str,
    latency_ms: int | None = None,
) -> None:
    """Un turno de chat. Solo slugs y metadatos, jamás el mensaje."""
    if not enabled():
        return
    emit(
        "consultas",
        {
            "ts": _now(),
            "user_hash": user_hash(email),
            "session_id": session_id,
            "symptom_slug": list(symptoms),
            "term_slug": list(terms),
            "risk_tier": risk_tier,
            "kind": kind,
            "latency_ms": latency_ms,
        },
    )


def recuperacion(
    *, query: str, k: int, hit_lexico: bool, sin_cobertura: bool, top_slugs: list[str]
) -> None:
    """Diagnóstico del RAG en producción: dónde falla la cobertura."""
    if not enabled():
        return
    emit(
        "recuperacion",
        {
            "ts": _now(),
            "query_hash": text_hash(query),  # hash, no la consulta
            "k": k,
            "hit_lexico": hit_lexico,
            "sin_cobertura": sin_cobertura,
            "top_slugs": list(top_slugs),
        },
    )


def guardarrail(*, tipo: str, grupo: str | None = None, email: str | None = None) -> None:
    """Cada disparo de un guardarraíl determinista: evidencia viva de FR-06/NFR-01."""
    if not enabled():
        return
    emit(
        "guardarrailes",
        {
            "ts": _now(),
            "tipo": tipo,
            "grupo": grupo,
            "user_hash": user_hash(email) if email else None,
        },
    )


def _now() -> str:
    import datetime

    return datetime.datetime.now(datetime.timezone.utc).isoformat()
