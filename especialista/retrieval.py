"""Recuperación híbrida del diccionario emocional (FR-08a/09/09b/10/10b).

Fusión RRF de dos recuperadores sobre `data/index/*`:

1. **Denso**: coseno sobre FAISS (`IndexFlatIP` con vectores `bge-m3` normalizados L2),
2. **Léxico**: BM25 sobre título + cuerpo, más un **match normalizado de título/alias
   con peso reforzado** —la señal más fiable de un diccionario (FR-09).

Reglas clave:

- Los alias de redirección pura **nunca** se devuelven: se resuelven a su
  `target_slug` antes de la respuesta (FR-08a). Los stub no tienen vector propio.
- Si el mejor score fusionado queda por debajo de τ, la consulta se marca como
  **SIN COBERTURA** (FR-09b): FAISS siempre devuelve k resultados y sin este piso
  una consulta fuera de dominio recibe 5 términos espurios.
- `format_for_llm` entrega contexto delimitado/etiquetado y recorta al presupuesto
  (FR-10b): ≤800 tokens/doc, ≤4.000/turno, corte por párrafo, título preservado.

Los valores k/τ/peso se fijan empíricamente con `eval/retrieval.py` (gold set §13.0),
no a ojo.
"""
from __future__ import annotations

import json
import pickle
import re
import unicodedata
from pathlib import Path

import faiss
import httpx
import numpy as np

from especialista.config import ROOT, settings
from especialista.index import (
    BM25_PATH,
    FAISS_PATH,
    META_PATH,
    norm,
    slugify,
    tokenize,
)

ALIASES_PATH = ROOT / "rag" / "aliases.json"

# ── Parámetros de recuperación (fijados con gold set, ver heartbeat) ──
DEFAULT_K = 5
TAU = 0.30          # umbral de cobertura sobre el score fusionado (FR-09b)
LEX_BOOST = 0.50    # peso reforzado del match normalizado título/alias (FR-09)
RRF_K = 60          # constante RRF (>= 60, convención)
DENSE_TOP = 120     # candidatos densos a fusionar
LEX_TOP = 120       # candidatos léxicos a fusionar
BIG_LEX = 1000.0    # separa niveles de fuerza de match en el ranking compuesto
TAU_DENSE_FALLBACK = 0.70  # coseno denso mínimo para "cobertura" sin match nominal

EMBED_MODEL = settings.embed_model
OLLAMA_EMBED_URL = settings.ollama_base_url.rstrip("/") + "/api/embed"


# ── Normalización ─────────────────────────────────────────────────
def _safe_norm(s: str) -> str:
    return norm(s)


def _word(s: str) -> str:
    return _safe_norm(s)


# ── Carga perezosa de artefactos ──────────────────────────────────
_index_cache: dict = {}


def _meta() -> dict:
    if "meta" not in _index_cache:
        _index_cache["meta"] = json.loads(META_PATH.read_text(encoding="utf-8"))
    return _index_cache["meta"]


def _faiss():
    if "faiss" not in _index_cache:
        _index_cache["faiss"] = faiss.read_index(str(FAISS_PATH))
    return _index_cache["faiss"]


def _matrix() -> np.ndarray:
    if "matrix" not in _index_cache:
        idx = _faiss()
        _index_cache["matrix"] = np.asarray(idx.reconstruct_n(0, idx.ntotal))
    return _index_cache["matrix"]


def _bm25():
    if "bm25" not in _index_cache:
        with open(BM25_PATH, "rb") as f:
            _index_cache["bm25"] = pickle.load(f)
    return _index_cache["bm25"]


def _docs() -> list[dict]:
    return _meta()["docs"]


def _aliases() -> dict:
    if "aliases" not in _index_cache:
        data = json.loads(ALIASES_PATH.read_text(encoding="utf-8"))
        _index_cache["aliases"] = data["aliases"]
    return _index_cache["aliases"]


def _embed(texts: list[str]) -> np.ndarray:
    out: list[np.ndarray] = []
    batch = 32
    for start in range(0, len(texts), batch):
        chunk = texts[start : start + batch]
        r = httpx.post(
            OLLAMA_EMBED_URL,
            json={"model": EMBED_MODEL, "input": chunk},
            timeout=180,
        )
        r.raise_for_status()
        for emb in r.json()["embeddings"]:
            out.append(np.asarray(emb, dtype=np.float32))
    return np.vstack(out)


# ── Índice de "nombres" de término (señal fiable del diccionario) ──
# Palabras genéricas que NO constituyen por sí solas un término de entrada
# (modificadores de título). Evitan falsos positivos de cobertura.
_STOP_WORDS = {
    # modificadores de título y palabras genéricas sin valor de entrada
    "alta", "alto", "baja", "bajo", "general", "dolores", "problemas",
    "problema", "ver", "enfermedades", "manifiesta", "manifestacion",
    "sintoma", "sintomas", "del", "los", "las", "uno", "una", "unos",
    "tengo", "razon", "modo", "que", "cual", "quien", "se", "mi", "mis",
    "desarrollo", "sistema", "cuerpo", "lado", "derecho", "izquierdo",
    "medico", "medica", "medicina", "receta", "instrucciones", "descripcion",
    "significado", "significa", "emocional", "emocionalmente", "desde", "hace",
    "cuando", "donde", "como", "para", "todo", "toda", "todos", "todas",
    "ano", "anos", "bien", "mal", "sentir", "siento", "sienten",
}

# Sufijos flexivos/derivativos del light stemming (español). Solo plurales
# (es/s) y deverbales (ido/idad/imiento…); NO desinencias de infinitivo ni
# vocales, para no confundir «olvida» (verbo) con «olvido» (sustantivo).
_STEM_SUFFIXES = (
    "imientos", "imiento", "amientos", "amiento", "iendo", "ando",
    "idos", "idas", "ados", "adas", "ido", "ida", "ado", "ada",
    "es", "s",
)


def _stem(word: str) -> str:
    for suf in _STEM_SUFFIXES:
        if len(word) - len(suf) >= 4 and word.endswith(suf):
            return word[: -len(suf)]
    return word

_TITLE_SPLIT_RE = re.compile(r"\s*[—–()\[\],;:/]\s*|\s+-\s+")

# Palabras conectoras que no cuentan como término por sí solas.
_CONNECTORS = {
    "de", "del", "la", "el", "los", "las", "a", "al", "o", "y", "e", "en",
    "con", "un", "una", "unos", "unas", "por", "para", "ver", "se", "que",
    "cual", "quien", "como", "sin", "entre", "sobre", "hacia",
}


def _meaningful(word: str) -> bool:
    return len(word) >= 3 and word not in _STOP_WORDS and word not in _CONNECTORS


def _title_phrases(title: str) -> list[str]:
    """Chunks del título (frases completas, no se trocean palabras)."""
    parts = _TITLE_SPLIT_RE.split(title)
    return [norm(p) for p in parts if norm(p)]


def _build_name_index() -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """Devuelve (phrase->slugs, single_word->slugs) para match de nombre/alias.

    Reglas (señal fiable del diccionario, FR-09):

    - Frase multi-palabra con ≥2 palabras significativas → se indexa completa
      (fuerza 2) y su **cabeza** (primera palabra significativa) como término
      (fuerza 1). Así «dolor de muelas» no empareja un «dolor de» suelto, pero
      «infarto» sí alcanza «corazón — infarto agudo de miocardio».
    - Las fuentes de ALIAS son frases «como lo dice el usuario»: sus palabras
      significativas se indexan todas (fuerza 1), porque son claves curadas.
    """
    phrase_to_slugs: dict[str, list[str]] = {}
    single_to_slugs: dict[str, list[str]] = {}

    def add_single(word: str, slug: str) -> None:
        if _meaningful(word):
            single_to_slugs.setdefault(_stem(word), []).append(slug)

    def add_phrase(phrase: str, slug: str, all_words: bool = False) -> None:
        p = norm(phrase)
        if not p:
            return
        words = p.split()
        significant = [w for w in words if _meaningful(w)]
        if not significant:
            return
        if " " in p and len(significant) >= 2:
            phrase_to_slugs.setdefault(p, []).append(slug)
            if all_words:
                for w in significant:
                    add_single(w, slug)
            else:
                add_single(significant[0], slug)
        else:
            add_single(significant[0], slug)

    for d in _docs():
        for phrase in _title_phrases(d["title"]):
            add_phrase(phrase, d["slug"], all_words=False)

    # Fuentes de alias: claves y títulos del stub son frases curadas.
    for key, val in _aliases().items():
        target = val.get("target_slug")
        if not target:
            continue
        src = key.split("-ver-")[0].replace("-", " ")
        add_phrase(src, target, all_words=True)
        txt_file = ROOT / "data" / f"{key}.md"
        if txt_file.exists():
            m = re.search(r'^title:\s*"?(.+?)"?\s*$', txt_file.read_text(encoding="utf-8"), re.M)
            if m:
                for phrase in _title_phrases(m.group(1)):
                    add_phrase(phrase, target, all_words=True)

    return phrase_to_slugs, single_to_slugs


_name_cache: dict = {}


def _name_index():
    if "names" not in _name_cache:
        _name_cache["names"] = _build_name_index()
    return _name_cache["names"]


def _resolve(target: str, depth: int = 0) -> str:
    """Sigue la cadena de alias hasta el slug indexado (FR-08a)."""
    if target in _meta()["slug_to_id"]:
        return target
    if depth > 5:
        return target
    val = _aliases().get(target)
    if val and val.get("target_slug"):
        return _resolve(val["target_slug"], depth + 1)
    return target


def _lexical_hits(query: str) -> dict[str, int]:
    """Documentos cuyo nombre/alias matchea el query, con fuerza (FR-09)."""
    qn = norm(query)
    qn_padded = " " + qn + " "
    phrase_to_slugs, single_to_slugs = _name_index()
    hits: dict[str, int] = {}

    def bump(slug: str, strength: int) -> None:
        resolved = _resolve(slug)
        if resolved in _meta()["slug_to_id"]:
            hits[resolved] = max(hits.get(resolved, 0), strength)

    for phrase, slugs in phrase_to_slugs.items():
        if f" {phrase} " in qn_padded:
            for s in slugs:
                bump(s, 2)

    tokens = [w for w in qn.split() if len(w) >= 3]
    for w in tokens:
        stem = _stem(w)
        # match por raíz (stem) — cubre plural y flexión (estreñido/estreñimiento)
        for s in single_to_slugs.get(stem, []):
            bump(s, 1)

    return hits


# ── Recuperación ──────────────────────────────────────────────────
def _rank(query: str) -> tuple[np.ndarray, np.ndarray, dict[str, int]]:
    """Devuelve (rrf_scores, dense_cos, lexical_hits) en orden de faiss_id.

    El lex_hits se resuelve a slugs indexados (FR-08a) y se usa para (a) decidir
    cobertura y (b) priorizar en el ranking (la señal fiable de un diccionario).
    """
    docs = _docs()
    n = len(docs)
    qv = _embed([query])[0].astype(np.float64)
    qv /= np.linalg.norm(qv) or 1.0
    dense = _matrix() @ qv  # coseno (vectores ya L2-normalizados)

    bm25 = _bm25()
    if hasattr(bm25, "get_scores"):
        lex_scores = np.asarray(bm25.get_scores(tokenize(query)), dtype=np.float64)
    else:
        lex_scores = None

    rrf = np.zeros(n, dtype=np.float64)
    for r, di in enumerate(np.argsort(-dense)[:DENSE_TOP]):
        rrf[di] += 1.0 / (RRF_K + r)
    if lex_scores is not None:
        for r, bi in enumerate(np.argsort(-lex_scores)[:LEX_TOP]):
            rrf[bi] += 1.0 / (RRF_K + r)

    return rrf, dense, _lexical_hits(query)


def _resolved_strength(lex_hits: dict[str, int]) -> dict[int, int]:
    """lex_hits (slug->strength) proyectado a faiss_id (resuelve alias)."""
    out: dict[int, int] = {}
    for slug, strength in lex_hits.items():
        resolved = _resolve(slug)
        sid = _meta()["slug_to_id"].get(resolved)
        if sid is not None:
            out[sid] = max(out.get(sid, 0), strength)
    return out


def search(query: str, k: int = DEFAULT_K, tau: float = TAU) -> dict:
    """Recupera top-k con resolución de alias y umbral de cobertura (FR-09b)."""
    docs = _docs()
    rrf, dense, lex_hits = _rank(query)
    strength_by_id = _resolved_strength(lex_hits)

    n = len(docs)
    # ranking: primero los que tienen match de nombre/alias (fuerza desc),
    # y dentro del mismo nivel, el RRF (denso+léxico) decide.
    strength_arr = np.zeros(n, dtype=np.float64)
    for sid, st in strength_by_id.items():
        strength_arr[sid] = float(st)
    composite = strength_arr * BIG_LEX + rrf

    order = np.argsort(-composite)
    results: list[dict] = []
    for idx in order[: int(k)]:
        results.append(
            {
                "slug": docs[idx]["slug"],
                "title": docs[idx]["title"],
                "letter": docs[idx]["letter"],
                "risk_tier": docs[idx]["risk_tier"],
                "score": float(composite[idx]),
                "content": docs[idx]["content"],
            }
        )

    best_strength = float(strength_arr[order[0]]) if len(order) else 0.0
    best_dense = float(dense[order[0]]) if len(order) else 0.0

    # cobertura (FR-09b): match nominal de la señal fiable, o (respaldo) un coseno
    # denso muy alto. El resto se declara SIN COBERTURA.
    covered = best_strength >= 1.0 or best_dense >= TAU_DENSE_FALLBACK

    return {
        "covered": covered,
        "best_score": float(composite[order[0]]) if len(order) else 0.0,
        "best_strength": best_strength,
        "best_dense": best_dense,
        "results": results,
    }


# ── Formato para el LLM (FR-10 / FR-10b) ──────────────────────────
_MAX_DOC_TOKENS = 800
_MAX_TURN_TOKENS = 4000


def _approx_tokens(text: str) -> int:
    return len(text.split())


def _truncate_by_paragraph(text: str, limit_tokens: int) -> str:
    words = text.split()
    if len(words) <= limit_tokens:
        return text
    # cortar por párrafo (líneas en blanco / saltos)
    paras = re.split(r"\n\s*\n", text)
    out: list[str] = []
    used = 0
    for para in paras:
        pwords = len(para.split())
        if out and used + pwords > limit_tokens:
            break
        out.append(para)
        used += pwords
    if not out:
        out = ["\n".join(words[:limit_tokens])]
    return "\n\n".join(out)


def format_for_llm(results: list[dict]) -> str:
    """Contexto delimitado y etiquetado por documento (FR-10/10b)."""
    blocks: list[str] = []
    budget = _MAX_TURN_TOKENS

    for d in results:
        accessible = min(_MAX_DOC_TOKENS, budget)
        body = _truncate_by_paragraph(d["content"], max(accessible - 40, 40))
        identifier = f"TITULO: {d['title']} [slug={d['slug']}] [tier={d['risk_tier']}]"
        blocks.append(f"<documento>\n{identifier}\n\n{body}\n</documento>")
        budget -= _approx_tokens(identifier) + _approx_tokens(body)
        if budget <= 0:
            break

    return "\n\n".join(blocks)
