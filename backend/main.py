"""FastAPI backend del especialista en enfermedades emocionales.

Bootstrap (M1): superficie mínima — /health + cabeceras de seguridad.
Los endpoints de auth/chat/perfil se añaden en skills posteriores (M3/M4).
"""
from __future__ import annotations

from fastapi import FastAPI, Request

from especialista.config import settings

app = FastAPI(
    title="Especialista en enfermedades emocionales",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    if settings.environment == "cloud":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.get("/health")
async def health():
    """Liveness público mínimo (sin filtrar detalles internos)."""
    return {"status": "ok"}
