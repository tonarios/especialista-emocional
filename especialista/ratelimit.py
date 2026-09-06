"""Rate limiting en proceso: ventana deslizante por identidad (sin dependencias).

Claves:
  - endpoints autenticados -> email del token
  - /api/login, /api/register -> IP del cliente
Límites configurables por env (RATE_LIMIT_<SCOPE>_PER_MIN). En Cloud Run el
límite es por instancia; la protección de borde adicional la pone el LB.
"""
from __future__ import annotations

import os
import time
from collections import defaultdict, deque

_WINDOWS: dict[str, deque[float]] = defaultdict(deque)


_DEFAULTS = {"login": 10, "register": 10, "chat": 30, "api": 120}


def _limit(scope: str) -> int:
    env = os.getenv(f"RATE_LIMIT_{scope.upper()}_PER_MIN", "")
    if env:
        return int(env or 0)
    return _DEFAULTS.get(scope.lower(), 60)


def check_rate_limit(key: str, scope: str) -> None:
    """Lanza HTTPException 429 si `key` excede el límite del scope en la última minute."""
    limit = _limit(scope)
    if limit <= 0:
        return
    now = time.monotonic()
    window = _WINDOWS[f"{scope}:{key}"]
    while window and now - window[0] > 60.0:
        window.popleft()
    if len(window) >= limit:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=429,
            detail="Demasiadas peticiones; inténtalo de nuevo en un minuto",
        )
    window.append(now)
