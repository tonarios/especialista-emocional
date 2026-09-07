"""Autenticación del especialista: usuarios + tokens seguros.

- Contraseñas: PBKDF2-HMAC-SHA256 con salt aleatorio por usuario (stdlib).
- Tokens: JWT-ish HS256 firmados con HMAC-SHA256 (header.payload.sig, stdlib).
- Secreto de firma: NUNCA hardcodeado. Prioridad 1, `JWT_SECRET` del entorno
  (Secret Manager en nube); prioridad 2, uno generado y persistido en la
  configuración de la app.

El almacén concreto (PostgreSQL o Firestore) lo resuelve `especialista.stores`.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import time

from especialista.config import settings
from especialista.stores import get_store

APP_NAME = "ah_emociones"
TOKEN_TTL = 60 * 60 * 12  # 12 h


# ── Contraseñas ───────────────────────────────────────────────────
def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 210_000)
    return "pbkdf2$210000$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(dk).decode()


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt_b64, hash_b64 = stored.split("$")
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iters))
        return hmac.compare_digest(dk, expected)
    except Exception:
        return False


# ── Usuarios ──────────────────────────────────────────────────────
def create_user(email: str, password: str) -> dict:
    email = email.strip().lower()
    get_store().create_user(email, hash_password(password))
    return {"email": email}


def get_user(email: str) -> dict | None:
    return get_store().get_user(email.strip().lower())


def authenticate(email: str, password: str) -> dict | None:
    user = get_user(email)
    if user is None or not verify_password(password, user["password_hash"]):
        return None
    return {"email": user["email"]}


# ── Secreto de firma (Secret Manager > BD; nunca hardcodeado) ─────
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def valid_email(email: str) -> bool:
    return bool(_EMAIL_RE.match(email or ""))


def get_or_create_secret() -> bytes:
    # Prioridad 1: JWT_SECRET inyectada por el entorno (Secret Manager en cloud).
    if settings.jwt_secret_b64:
        return base64.b64decode(settings.jwt_secret_b64)
    # Prioridad 2: secreto persistido por la app la primera vez (local).
    store = get_store()
    stored = store.get_config("signing_secret")
    if stored is None:
        secret = secrets.token_bytes(32)
        store.set_config("signing_secret", base64.b64encode(secret).decode())
        return secret
    return base64.b64decode(stored)


# ── Tokens (JWT-ish HS256) ────────────────────────────────────────
def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def create_token(email: str) -> str:
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = _b64(json.dumps({"sub": email, "iat": int(time.time()), "exp": int(time.time()) + TOKEN_TTL}).encode())
    secret = get_or_create_secret()
    sig = _b64(hmac.new(secret, f"{header}.{payload}".encode(), hashlib.sha256).digest())
    return f"{header}.{payload}.{sig}"


def verify_token(token: str) -> str | None:
    """Devuelve el email del token si es válido, HS256 y no ha expirado; si no, None."""
    try:
        header_b64, payload_b64, sig = token.split(".")
        header = json.loads(_b64d(header_b64))
        if header.get("alg") != "HS256" or header.get("typ") != "JWT":
            return None
        secret = get_or_create_secret()
        expected = hmac.new(secret, f"{header_b64}.{payload_b64}".encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(_b64d(sig), expected):
            return None
        data = json.loads(_b64d(payload_b64))
        if data.get("exp", 0) < time.time():
            return None
        sub = data.get("sub")
        if not isinstance(sub, str) or not valid_email(sub):
            return None
        return sub
    except Exception:
        return None
