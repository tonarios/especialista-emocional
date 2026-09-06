"""FastAPI backend del especialista en enfermedades emocionales.

Superficie (PRD §10):
- Pública mínima: `/api/register`, `/api/login`, `/health`, estático.
- Tras Bearer: `/chat`, `/profile`, `/profile/consultations`, `/sessions`.

Usuario ADK = email autenticado (FR-17, aislamiento). SQL siempre parametrizado
(NFR-03). Rate-limit por email e IP (NFR-05).
"""
from __future__ import annotations

from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field

from especialista import agent, audit, auth, memory, ratelimit
from especialista.config import settings

app = FastAPI(
    title="Especialista en enfermedades emocionales",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

MIN_PASSWORD_LEN = 8


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


# ── DTOs ──────────────────────────────────────────────────────────
class RegisterBody(BaseModel):
    email: str
    password: str = Field(min_length=MIN_PASSWORD_LEN)


class LoginBody(BaseModel):
    email: str
    password: str


class ChatBody(BaseModel):
    message: str
    session_id: str | None = None


# ── Auth helpers ──────────────────────────────────────────────────
def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _bearer_email(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token requerido")
    email = auth.verify_token(authorization[len("Bearer ") :].strip())
    if email is None:
        raise HTTPException(status_code=401, detail="Token inválido o expirado")
    return email


# ── Endpoints públicos ────────────────────────────────────────────
@app.post("/api/register")
async def register(body: RegisterBody, request: Request):
    ratelimit.check_rate_limit(_client_ip(request), "register")
    email = body.email.strip().lower()
    if not auth.valid_email(email):
        raise HTTPException(status_code=400, detail="Correo inválido")
    try:
        auth.create_user(email, body.password)
    except ValueError:
        raise HTTPException(status_code=409, detail="El correo ya está registrado")
    token = auth.create_token(email)
    audit.audit("register", user_email=email, client_ip=_client_ip(request), status=201,
                detail={"action": "register"})
    return {"token": token, "email": email, "profile": memory.get_profile(email)}


@app.post("/api/login")
async def login(body: LoginBody, request: Request):
    ratelimit.check_rate_limit(_client_ip(request), "login")
    email = body.email.strip().lower()
    user = auth.authenticate(email, body.password)
    if user is None:
        audit.audit("login_failed", user_email=email, client_ip=_client_ip(request), status=401)
        raise HTTPException(status_code=401, detail="Credenciales inválidas")
    token = auth.create_token(email)
    audit.audit("login", user_email=email, client_ip=_client_ip(request), status=200)
    return {"token": token, "email": email, "profile": memory.get_profile(email)}


# ── Endpoints tras Bearer ─────────────────────────────────────────
@app.get("/profile")
async def profile(authorization: str | None = Header(default=None)):
    email = _bearer_email(authorization)
    audit.audit("profile_read", user_email=email, status=200)
    return memory.get_profile(email)


@app.delete("/profile/consultations")
async def delete_consultations(authorization: str | None = Header(default=None)):
    email = _bearer_email(authorization)
    memory.clear_consultations(email)
    audit.audit("profile_delete_consultations", user_email=email, status=200)
    return {"status": "ok"}


@app.get("/sessions")
async def sessions(authorization: str | None = Header(default=None)):
    email = _bearer_email(authorization)
    audit.audit("sessions_list", user_email=email, status=200)
    return {"sessions": await memory.list_sessions(email)}


@app.post("/chat")
async def chat(body: ChatBody, authorization: str | None = Header(default=None)):
    email = _bearer_email(authorization)
    ratelimit.check_rate_limit(email, "chat")
    session_id = body.session_id or "default"

    result = agent.run_deterministic(body.message, user_id=email, session_id=session_id)
    kind = result["kind"]
    text = result["text"]
    sources = agent.source_objects(result["sources"])

    # FR-12: persiste el turno en la sesión ADK (sobrevive reinicios).
    if kind in ("respuesta", "sin_cobertura", "emergency"):
        try:
            await memory.append_turn(memory.APP_NAME, email, session_id, "user", body.message)
            await memory.append_turn(memory.APP_NAME, email, session_id, "model", text)
        except Exception:
            pass

    if kind == "blocked":
        raise HTTPException(status_code=403, detail=result.get("detail", "prompt injection"))

    return {
        "session_id": session_id,
        "kind": kind,
        "done": True,
        "text": text,
        "risk_tier": result["risk_tier"],
        "sources": sources,
    }
