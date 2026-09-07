"""Conmutación de proveedor (Ollama ↔ Vertex) y las trampas que esconde.

El riesgo aquí no es que falle ruidosamente, sino que funcione **en silencio y
mal**: consultar con embeddings de un modelo un índice construido con otro
devuelve rankings basura sin lanzar ninguna excepción. Estos tests protegen
justo eso.
"""
from __future__ import annotations

import numpy as np
import pytest

from especialista import providers, retrieval
from especialista.config import settings


@pytest.fixture
def vertex(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "vertex")
    monkeypatch.setattr(settings, "llm_model", "gemini-2.5-flash-lite")
    monkeypatch.setattr(settings, "embed_model", "gemini-embedding-001")
    monkeypatch.setattr(settings, "embed_dims", 3072)


@pytest.fixture
def ollama(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "ollama")
    monkeypatch.setattr(settings, "llm_model", "ollama/gemma4:latest")
    monkeypatch.setattr(settings, "embed_model", "bge-m3")
    monkeypatch.setattr(settings, "embed_dims", None)


# ── Dimensiones ───────────────────────────────────────────────────

def test_dimensiones_por_proveedor(ollama):
    assert providers.embed_dims() == 1024


def test_dimensiones_vertex(vertex):
    assert providers.embed_dims() == 3072


def test_embed_dims_explicito_manda(monkeypatch, vertex):
    """Permite truncar (Matryoshka) sin tocar código."""
    monkeypatch.setattr(settings, "embed_dims", 768)
    assert providers.embed_dims() == 768


# ── El índice no es intercambiable entre proveedores ──────────────

def test_el_hash_del_corpus_cambia_con_el_modelo(monkeypatch):
    """Sin esto, cambiar de proveedor reutilizaría vectores incomparables."""
    from especialista import index

    monkeypatch.setattr(settings, "embed_model", "bge-m3")
    monkeypatch.setattr(settings, "embed_dims", 1024)
    monkeypatch.setattr(settings, "llm_provider", "ollama")
    h_ollama = index.corpus_hash()

    monkeypatch.setattr(settings, "embed_model", "gemini-embedding-001")
    monkeypatch.setattr(settings, "embed_dims", 3072)
    monkeypatch.setattr(settings, "llm_provider", "vertex")
    h_vertex = index.corpus_hash()

    assert h_ollama != h_vertex, (
        "el corpus_hash no distingue el modelo de embeddings: un índice de "
        "bge-m3 se reutilizaría con consultas de Vertex sin avisar"
    )


def test_el_hash_cambia_solo_con_las_dimensiones(monkeypatch):
    from especialista import index

    monkeypatch.setattr(settings, "embed_model", "gemini-embedding-001")
    monkeypatch.setattr(settings, "llm_provider", "vertex")
    monkeypatch.setattr(settings, "embed_dims", 3072)
    a = index.corpus_hash()
    monkeypatch.setattr(settings, "embed_dims", 768)
    assert index.corpus_hash() != a


# ── Umbral de cobertura calibrado por modelo (FR-09b) ─────────────

def test_umbral_denso_depende_del_modelo():
    """Cada espacio de embeddings tiene su distribución: un umbral fijo es un bug.

    Con 0.70 (el de bge-m3), «¿qué significa emocionalmente el cuerpo?» puntuaba
    0.7385 con gemini-embedding-001 y se colaba como cobertura, rompiendo la
    precisión fuera de dominio = 1.0 que el PRD §13.0 declara innegociable.
    """
    assert retrieval._TAU_DENSE_BY_MODEL["bge-m3"] == 0.70
    assert retrieval._TAU_DENSE_BY_MODEL["gemini-embedding-001"] == 0.75


def test_modelo_desconocido_usa_el_umbral_mas_estricto():
    """Ante un modelo sin calibrar, se peca de conservador: mejor recall bajo
    que un falso positivo en un dominio de salud."""
    desconocidos = retrieval._TAU_DENSE_DEFAULT
    assert desconocidos >= max(retrieval._TAU_DENSE_BY_MODEL.values())


# ── Normalización de vectores ─────────────────────────────────────

def test_vertex_normaliza_los_vectores(vertex, monkeypatch):
    """El índice es IndexFlatIP y asume norma 1 para que el producto interno
    sea coseno. gemini-embedding-001 NO normaliza los vectores truncados."""

    class FakeEmb:
        values = [3.0, 4.0] + [0.0] * 3070

    class FakeResp:
        embeddings = [FakeEmb()]

    class FakeModels:
        def embed_content(self, **_):
            return FakeResp()

    class FakeClient:
        models = FakeModels()

    monkeypatch.setattr(providers, "_vertex_client", lambda: FakeClient())
    monkeypatch.setattr(providers, "_genai_client", FakeClient(), raising=False)

    vec = providers.embed(["hola"])[0]
    assert float(np.linalg.norm(vec)) == pytest.approx(1.0, abs=1e-5), (
        "sin normalizar, el producto interno de FAISS deja de ser coseno"
    )


def test_nombre_de_modelo_sin_prefijo_de_proveedor(monkeypatch):
    for crudo, esperado in [
        ("ollama/gemma4:latest", "gemma4:latest"),
        ("vertex/gemini-2.5-flash-lite", "gemini-2.5-flash-lite"),
        ("gemini-2.5-flash-lite", "gemini-2.5-flash-lite"),
    ]:
        monkeypatch.setattr(settings, "llm_model", crudo)
        assert providers._model_name() == esperado


# ── Selección de backend de datos ─────────────────────────────────

def test_backend_desconocido_falla_claro(monkeypatch):
    from especialista import stores

    monkeypatch.setattr(settings, "storage_backend", "mysql")
    stores.reset_store()
    with pytest.raises(ValueError, match="STORAGE_BACKEND desconocido"):
        stores.get_store()
    stores.reset_store()
