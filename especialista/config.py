"""Configuración del especialista en enfermedades emocionales.

Regla de secretos: NUNCA hay credenciales por defecto en el código. Todo
secreto llega por variables de entorno (local: export/shell; cloud: Secret
Manager montado como env var por Cloud Run). Si falta uno requerido, la app
falla al arrancar con un mensaje claro.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# override=True: el .env del repo manda sobre variables ya exportadas en el shell
# SOLO en desarrollo local. En producción el contenedor no lleva .env y todo
# entra como env var inyectada.
load_dotenv(override=True)

ROOT = Path(__file__).resolve().parent.parent


def _require(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(
            f"Falta la variable de entorno requerida {name}. "
            "En local: defínela en .env o expórtala en el shell (nunca dentro de la imagen). "
            "En cloud: Secret Manager -> env var de Cloud Run."
        )
    return value


class Settings:
    def __init__(self) -> None:
        # ── Secretos (sin defaults; fail-fast) ──────────────────────
        cloudsql_instance = os.getenv("CLOUDSQL_INSTANCE", "").strip()
        if cloudsql_instance:
            self.postgres_dsn = (
                f"postgresql://{os.environ['POSTGRES_USER']}:{os.environ['POSTGRES_PASSWORD']}"
                f"@/{os.environ['POSTGRES_DB']}?host=/cloudsql/{cloudsql_instance}"
            )
        else:
            # Local: DSN completo definido en .env o exportado en el shell.
            self.postgres_dsn = _require("POSTGRES_DSN")
        # Secreto de firma JWT: si JWT_SECRET está presente (Secret Manager)
        # tiene prioridad; si no, se usa/genera el persistido en app_config.
        self.jwt_secret_b64 = os.getenv("JWT_SECRET", "")

        # ── Modelo LLM (local: gemma4 vía Ollama; cloud: gemini/… TBD) ──
        self.llm_model = os.getenv("LLM_MODEL", "ollama/gemma4:latest")
        # Fallback opcional (p. ej. otro modelo); sin valor = solo primario.
        self.fallback_model = os.getenv("FALLBACK_LLM_MODEL", "") or None

        # ── RAG / embeddings ─────────────────────────────────────────
        self.embed_model = os.getenv("EMBED_MODEL", "bge-m3")
        # Local con Docker = http://host.docker.internal:11434; sin Docker = localhost.
        self.ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.index_dir = os.getenv("INDEX_DIR", "data/index")

        # ── No secretos ─────────────────────────────────────────────
        self.environment = os.getenv("ENVIRONMENT", "local")


settings = Settings()
