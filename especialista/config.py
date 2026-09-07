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
        # ── Backend de datos ────────────────────────────────────────
        # local  -> postgres (docker compose)
        # cloud  -> firestore (escala a cero; docs/presupuesto-gcp.md §5)
        self.storage_backend = os.getenv("STORAGE_BACKEND", "postgres").strip().lower()

        # ── Secretos (sin defaults; fail-fast) ──────────────────────
        # El DSN solo se exige si el backend es Postgres: en nube no existe.
        if self.storage_backend == "postgres":
            self.postgres_dsn = _require("POSTGRES_DSN")
        else:
            self.postgres_dsn = os.getenv("POSTGRES_DSN", "")
        # Secreto de firma JWT: si JWT_SECRET está presente (Secret Manager)
        # tiene prioridad; si no, se usa/genera el persistido en app_config.
        self.jwt_secret_b64 = os.getenv("JWT_SECRET", "")

        # ── Proveedor de LLM y embeddings ───────────────────────────
        # ollama -> gemma4 / bge-m3 en local
        # vertex -> gemini-2.5-flash-lite / gemini-embedding-001 en Cloud Run
        self.llm_provider = os.getenv("LLM_PROVIDER", "ollama").strip().lower()
        self.llm_model = os.getenv("LLM_MODEL", "ollama/gemma4:latest")
        # Fallback opcional (p. ej. otro modelo); sin valor = solo primario.
        self.fallback_model = os.getenv("FALLBACK_LLM_MODEL", "") or None

        # ── RAG / embeddings ─────────────────────────────────────────
        self.embed_model = os.getenv("EMBED_MODEL", "bge-m3")
        # Dimensiones del vector. bge-m3 = 1024; gemini-embedding-001 = 3072
        # (sin truncar, decisión del owner). El índice se invalida solo al
        # cambiar, porque el hash de corpus cubre la configuración.
        self.embed_dims = int(os.getenv("EMBED_DIMS", "0")) or None
        # Local con Docker = http://host.docker.internal:11434; sin Docker = localhost.
        self.ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.index_dir = os.getenv("INDEX_DIR", "data/index")

        # ── GCP (solo con backend/proveedor de nube) ─────────────────
        self.gcp_project = os.getenv("GOOGLE_CLOUD_PROJECT", "").strip()
        self.gcp_location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1").strip()
        self.firestore_database = os.getenv("FIRESTORE_DATABASE", "(default)").strip()
        # Analítica en BigQuery: vacío = desactivada (el caso local).
        self.bq_dataset = os.getenv("BQ_DATASET", "").strip()
        # Sal del hash de usuario para BigQuery. Sin ella no se emite nada:
        # es preferible perder analítica a escribir un identificador reversible.
        self.analytics_salt = os.getenv("ANALYTICS_SALT", "")

        # ── No secretos ─────────────────────────────────────────────
        self.environment = os.getenv("ENVIRONMENT", "local")


settings = Settings()
