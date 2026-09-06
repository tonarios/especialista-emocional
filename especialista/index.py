"""Indexado del RAG (FR-08/08a/08b/11).

Construye, a partir de `data/*.md` + `rag/aliases.json` + `rag/risk_tiers.json`:

- `data/index/diccionario.index` — índice FAISS (IndexFlatIP sobre embeddings
  `bge-m3` normalizados L2 = coseno, 1024 dims).
- `data/index/meta.json` — `faiss_id -> {title, slug, letter, content, risk_tier}`
  + `corpus_hash` + conteos. Incluye el contenido completo del corpus.
- `data/index/bm25.pkl` — índice léxico `rank_bm25` sobre título (reforzado) + cuerpo.

Reglas de indexado (FR-08a/08b):
- Los 55 documentos de redirección pura NO reciben vector propio (son alias).
- Un vector por documento, EXCEPTO `huesos-en-general.md`, que se parte por
  sección (~9 chunks identificables por sub-término; los alias que apuntan a él
  — osteoporosis, fractura, dislocación — resuelven al chunk correcto).

El hash del corpus cubre `data/` Y los artefactos de `rag/` que afectan el índice
(aliases, risk_tiers), de modo que un índice OBSOLETO se detecta, no solo uno faltante.

Uso: `python -m index`
"""
from __future__ import annotations

import base64
import hashlib
import json
import pickle
import re
import sys
import unicodedata
from pathlib import Path

import faiss
import httpx
import numpy as np
from rank_bm25 import BM25Okapi

from especialista.config import ROOT, settings

DATA = ROOT / "data"
RAG = ROOT / "rag"
INDEX_DIR = Path(settings.index_dir) if Path(settings.index_dir).is_absolute() else ROOT / settings.index_dir
ALIASES_PATH = RAG / "aliases.json"
RISK_TIERS_PATH = RAG / "risk_tiers.json"

FAISS_PATH = INDEX_DIR / "diccionario.index"
META_PATH = INDEX_DIR / "meta.json"
BM25_PATH = INDEX_DIR / "bm25.pkl"
EMBED_CACHE_PATH = INDEX_DIR / ".embeddings_cache.json"

EMBED_MODEL = settings.embed_model
OLLAMA_EMBED_URL = settings.ollama_base_url.rstrip("/") + "/api/embed"

# Único documento compuesto (FR-08b): se parte por sección.
COMPOSED_SLUG = "huesos-en-general"
# Etiquetas internas que NO son sub-términos (se descartan como inicio de sección).
_LABELS = {"resentir", "conflicto", "analogia", "manifestacion fisica", "manifestación física"}


def norm(s: str) -> str:
    """Minúsculas + sin tildes + no alfanuméricos a espacio (para comparación)."""
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def slugify(s: str) -> str:
    """Convierte un término a clave de slug ASCII (sin tildes)."""
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", norm(text))


# ── Lectura del corpus ───────────────────────────────────────────
_FM_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n(.*)\Z", re.DOTALL)


def _field(fm: str, key: str) -> str:
    m = re.search(rf"^{key}:\s*\"?(.+?)\"?\s*$", fm, re.M)
    return m.group(1).strip() if m else ""


def parse_doc(path: Path) -> dict | None:
    text = path.read_text(encoding="utf-8")
    m = _FM_RE.match(text)
    fm, body = (m.group(1), m.group(2)) if m else ("", text)
    title = _field(fm, "title")
    if not title:
        return None
    slug = _field(fm, "slug") or path.stem
    letter = _field(fm, "letter")
    body = re.sub(r"^\s*#\s+.*$", "", body, flags=re.M).strip()
    return {"slug": slug, "title": title, "letter": letter, "body": body}


def read_docs() -> dict[str, dict]:
    docs: dict[str, dict] = {}
    for f in sorted(DATA.glob("*.md")):
        d = parse_doc(f)
        if d is None:
            print(f"  aviso: {f.name} sin title en frontmatter", file=sys.stderr)
            continue
        docs[d["slug"]] = d
    return docs


def load_aliases() -> dict:
    data = json.loads(ALIASES_PATH.read_text(encoding="utf-8"))
    return data["aliases"]


def load_risk_tier_map() -> dict[str, str]:
    data = json.loads(RISK_TIERS_PATH.read_text(encoding="utf-8"))
    m: dict[str, str] = {}
    for tier, slugs in data["tiers"].items():
        for s in slugs:
            m[s] = tier
    return m


# ── Chunking del documento compuesto ─────────────────────────────
_TOPIC_RE = re.compile(r"^(?:La|Una|Un|Los|Las|El)\b.*?\*\*(.+?)\*\*")


def _chunk_composed(doc: dict) -> list[dict]:
    """Parte `huesos-en-general.md` en ~9 chunks (intro + sub-términos)."""
    lines = doc["body"].split("\n")
    topic_starts: list[tuple[int, str]] = []
    for i, line in enumerate(lines):
        m = _TOPIC_RE.match(line)
        if not m:
            continue
        term = m.group(1).strip(" *.")
        if norm(term) in _LABELS:
            continue
        topic_starts.append((i, term))

    # Un sub-término puede ocupar dos párrafos introductorios (p. ej. "Los problemas
    # en el **húmero**" + "El **húmero** simboliza"): se colapsan consecutivos del
    # mismo término.
    merged: list[tuple[int, str]] = []
    for line_idx, term in topic_starts:
        if merged and merged[-1][1] == term:
            continue
        merged.append((line_idx, term))

    chunks: list[dict] = []
    for idx, (start, term) in enumerate(merged):
        end = merged[idx + 1][0] if idx + 1 < len(merged) else len(lines)
        text = "\n".join(lines[start:end]).strip()
        key = slugify(term)
        if key == slugify("huesos"):
            # La intro es el término "en general": conserva el slug base sin sección.
            chunk_slug = COMPOSED_SLUG
            chunk_title = doc["title"]
        else:
            chunk_slug = f"{COMPOSED_SLUG}#{key}"
            chunk_title = f"HUESOS — {term.upper()}"
        chunks.append(
            {
                "slug": chunk_slug,
                "title": chunk_title,
                "letter": doc["letter"],
                "body": text,
                "risk_tier": None,
            }
        )
    return chunks


# ── Embeddings (bge-m3 vía Ollama, con cache por hash) ───────────
def _load_cache() -> dict[str, str]:
    if EMBED_CACHE_PATH.exists():
        try:
            return json.loads(EMBED_CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_cache(cache: dict[str, str]) -> None:
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    EMBED_CACHE_PATH.write_text(json.dumps(cache), encoding="utf-8")


def _b64(v: np.ndarray) -> str:
    return base64.b64encode(np.asarray(v, dtype=np.float32).tobytes()).decode()


def _unb64(s: str) -> np.ndarray:
    return np.frombuffer(base64.b64decode(s), dtype=np.float32)


def embed_texts(texts: list[str], cache: dict[str, str]) -> np.ndarray:
    """Devuelve una matriz (n, dim) de embeddings, usando y actualizando el cache."""
    hashes = [hashlib.sha256(t.encode("utf-8")).hexdigest() for t in texts]
    out: list[np.ndarray | None] = [None] * len(texts)
    todo: list[tuple[int, str]] = []
    for i, h in enumerate(hashes):
        if h in cache:
            out[i] = _unb64(cache[h])
        else:
            todo.append((i, texts[i]))
    batch = 32
    for start in range(0, len(todo), batch):
        chunk = todo[start : start + batch]
        idxs = [i for i, _ in chunk]
        payload = [t for _, t in chunk]
        r = httpx.post(OLLAMA_EMBED_URL, json={"model": EMBED_MODEL, "input": payload}, timeout=180)
        r.raise_for_status()
        embeds = r.json()["embeddings"]
        for (i, _), emb in zip(chunk, embeds):
            arr = np.asarray(emb, dtype=np.float32)
            out[i] = arr
            cache[hashes[i]] = _b64(arr)
    return np.vstack([np.asarray(v) for v in out])


# ── Hash del corpus (FR-11) ──────────────────────────────────────
def corpus_hash() -> str:
    h = hashlib.sha256()
    for f in sorted(DATA.glob("*.md")):
        h.update(f.name.encode("utf-8"))
        h.update(b"\0")
        h.update(f.read_bytes())
    for p in (ALIASES_PATH, RISK_TIERS_PATH):
        h.update(p.read_bytes())
    return h.hexdigest()


# ── Build principal ──────────────────────────────────────────────
def build() -> dict:
    docs = read_docs()
    aliases = load_aliases()
    tier_map = load_risk_tier_map()

    # Unidades a vectorizar (en orden determinista por slug).
    units: list[dict] = []
    for slug in sorted(docs):
        if slug in aliases:
            continue  # redirección pura: sin vector (FR-08a)
        doc = docs[slug]
        if slug == COMPOSED_SLUG:
            units.extend(_chunk_composed(doc))
        else:
            units.append(
                {
                    "slug": slug,
                    "title": doc["title"],
                    "letter": doc["letter"],
                    "body": doc["body"],
                    "risk_tier": None,
                }
            )

    for u in units:
        base_slug = u["slug"].split("#", 1)[0]
        u["risk_tier"] = tier_map.get(base_slug, "estandar")

    print(f"documentos:            {len(docs)}")
    print(f"redirecciones (alias): {len(aliases)}")
    print(f"vectores a construir:  {len(units)}")

    cache = _load_cache()
    embed_texts_list = [f"{u['title']}\n{u['body']}" for u in units]
    matrix = embed_texts(embed_texts_list, cache)
    _save_cache(cache)

    dim = int(matrix.shape[1])
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    normalized = matrix / norms
    normalized = np.ascontiguousarray(normalized, dtype=np.float32)

    index = faiss.IndexFlatIP(dim)
    index.add(normalized)

    # BM25 (título reforzado x2 + cuerpo).
    corpus = [tokenize(f"{u['title']} {u['title']} {u['body']}") for u in units]
    bm25 = BM25Okapi(corpus)

    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(FAISS_PATH))
    with open(BM25_PATH, "wb") as f:
        pickle.dump(bm25, f)

    docs_meta = [
        {
            "faiss_id": i,
            "title": u["title"],
            "slug": u["slug"],
            "letter": u["letter"],
            "content": u["body"],
            "risk_tier": u["risk_tier"],
        }
        for i, u in enumerate(units)
    ]

    slug_to_id = {m["slug"]: m["faiss_id"] for m in docs_meta}
    unresolved = [s for s in sorted(aliases) if aliases[s].get("target_slug") is None]
    meta = {
        "version": 1,
        "embed_model": EMBED_MODEL,
        "dim": dim,
        "vector_count": len(units),
        "corpus_hash": corpus_hash(),
        "counts": {
            "docs": len(docs),
            "redirects": len(aliases),
            "aliases_resolved": len(aliases) - len(unresolved),
            "aliases_unresolved": len(unresolved),
            "composed_chunks": sum(1 for u in units if "#" in u["slug"]),
            "vectors": len(units),
        },
        "docs": docs_meta,
        "slug_to_id": slug_to_id,
    }
    META_PATH.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"vectores:              {len(units)}")
    print(f"  chunks compuesto:    {meta['counts']['composed_chunks']}")
    print(f"dim embeddings:        {dim}")
    print(f"corpus_hash:           {meta['corpus_hash'][:16]}…")
    print(f"alias sin destino:     {len(unresolved)}")
    print(f"escrito: {META_PATH.relative_to(ROOT)}, {FAISS_PATH.relative_to(ROOT)}, {BM25_PATH.relative_to(ROOT)}")
    return meta


def main() -> int:
    meta = build()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
