"""Proveedores de LLM y embeddings: Ollama (local) o Vertex AI (nube).

Un único punto de conmutación para que ni `agent.py` ni `index.py` sepan contra
qué están hablando. Lo elige `LLM_PROVIDER`.

| | local | nube |
|---|---|---|
| LLM | `gemma4:latest` vía Ollama `/api/chat` | `gemini-2.5-flash-lite` |
| Embeddings | `bge-m3` (1024 dims) | `gemini-embedding-001` (3072 dims) |

Dos detalles que no son obvios y que costaron depuración:

1. **gemma4 es un modelo *thinking*.** Sin `think: False` gasta el presupuesto de
   tokens razonando y devuelve `content` vacío. Y `LiteLlm 1.100 +
   ollama_chat/gemma4` devolvía `content=''` de forma no determinista, así que
   el camino local usa el endpoint nativo por httpx.
2. **Cambiar de proveedor cambia el espacio vectorial.** Un índice construido
   con `bge-m3` no se puede consultar con embeddings de Vertex: los vectores no
   son comparables. El hash de corpus incluye el modelo y las dimensiones, así
   que el índice se invalida solo — pero hay que reindexar (~USD 0.09).
"""
from __future__ import annotations

import numpy as np

from especialista.config import settings

# Límite de entrada de gemini-embedding-001.
_VERTEX_EMBED_MAX_TOKENS = 2048
# Recorte defensivo por si un documento excede el límite (≈3,8 ch/token en es).
_VERTEX_EMBED_MAX_CHARS = _VERTEX_EMBED_MAX_TOKENS * 3

_genai_client = None


def provider() -> str:
    return settings.llm_provider


def _vertex_client():
    """Cliente de google-genai apuntando a Vertex (autenticación por SA)."""
    global _genai_client
    if _genai_client is None:
        from google import genai

        _genai_client = genai.Client(
            vertexai=True,
            project=settings.gcp_project or None,
            location=settings.gcp_location,
        )
    return _genai_client


def _model_name() -> str:
    """Nombre del modelo sin prefijo de proveedor."""
    m = settings.llm_model
    for prefix in ("ollama/", "vertex/", "gemini/"):
        if m.startswith(prefix):
            return m[len(prefix) :]
    return m


# ── Chat ──────────────────────────────────────────────────────────

def chat(messages: list[dict], *, max_tokens: int, temperature: float) -> str:
    """Una respuesta de texto. `messages` = [{role: system|user, content: str}]."""
    if settings.llm_provider == "vertex":
        return _vertex_chat(messages, max_tokens=max_tokens, temperature=temperature)
    return _ollama_chat(messages, max_tokens=max_tokens, temperature=temperature)


def _ollama_chat(messages: list[dict], *, max_tokens: int, temperature: float) -> str:
    import httpx

    url = settings.ollama_base_url.rstrip("/") + "/api/chat"
    payload = {
        "model": _model_name(),
        "messages": messages,
        "stream": False,
        # gemma4 (Gemma 3) es "thinking": sin esto, `content` viene vacío.
        "think": False,
        "options": {"temperature": temperature, "num_predict": max_tokens},
    }
    for _ in range(3):
        r = httpx.post(url, json=payload, timeout=300)
        r.raise_for_status()
        content = ((r.json().get("message") or {}).get("content") or "").strip()
        if content:
            return content
    return ""


def _vertex_chat(messages: list[dict], *, max_tokens: int, temperature: float) -> str:
    from google.genai import types

    system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
    user = "\n\n".join(m["content"] for m in messages if m["role"] != "system")

    config = types.GenerateContentConfig(
        system_instruction=system or None,
        temperature=temperature,
        max_output_tokens=max_tokens,
    )
    for _ in range(3):
        resp = _vertex_client().models.generate_content(
            model=_model_name(), contents=user, config=config
        )
        text = (resp.text or "").strip()
        if text:
            return text
    return ""


# ── Embeddings ────────────────────────────────────────────────────

def embed_dims() -> int:
    """Dimensiones esperadas del vector, para validar el índice."""
    if settings.embed_dims:
        return settings.embed_dims
    return 3072 if settings.llm_provider == "vertex" else 1024


def embed(texts: list[str]) -> list[np.ndarray]:
    """Un vector float32 por texto, en el mismo orden."""
    if settings.llm_provider == "vertex":
        return _vertex_embed(texts)
    return _ollama_embed(texts)


def _ollama_embed(texts: list[str]) -> list[np.ndarray]:
    import httpx

    url = settings.ollama_base_url.rstrip("/") + "/api/embed"
    r = httpx.post(url, json={"model": settings.embed_model, "input": texts}, timeout=180)
    r.raise_for_status()
    return [np.asarray(e, dtype=np.float32) for e in r.json()["embeddings"]]


def _vertex_embed(texts: list[str]) -> list[np.ndarray]:
    from google.genai import types

    config = types.EmbedContentConfig(output_dimensionality=embed_dims())
    out: list[np.ndarray] = []
    # Vertex acepta lotes pequeños; se envía de uno en uno para que un documento
    # largo no arrastre a todo el lote a un error.
    for t in texts:
        resp = _vertex_client().models.embed_content(
            model=settings.embed_model,
            contents=t[:_VERTEX_EMBED_MAX_CHARS],
            config=config,
        )
        vec = np.asarray(resp.embeddings[0].values, dtype=np.float32)
        # gemini-embedding-001 NO normaliza los vectores truncados (a diferencia
        # de modelos más nuevos). El índice es IndexFlatIP y asume norma 1 para
        # que el producto interno sea coseno, así que se normaliza aquí.
        norm = float(np.linalg.norm(vec))
        if norm > 0:
            vec = vec / norm
        out.append(vec)
    return out
