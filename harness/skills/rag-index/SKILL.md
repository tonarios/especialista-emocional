---
name: rag-index
description: Genera el índice FAISS (embeddings bge-m3) + BM25 + meta.json con risk_tier, hash del corpus, alias de redirección sin vector propio y chunking por sección de huesos-en-general. FR-08/08a/08b/11.
---

# rag-index — M2a: indexado reproducible e idempotente

## Cuándo activar

- Después de `medical-safety` (`meta.json` consume `risk_tiers.json`).
- Siempre que cambien `data/*.md`, `rag/aliases.json` o `rag/risk_tiers.json`.

## Entradas

- `data/*.md` — 1.265 términos; frontmatter `title/slug/letter` completo; cuerpo **sin estructura uniforme** (§3).
- `rag/aliases.json` — 55 redirecciones puras, cadenas colapsadas, ciclos neutralizados (HECHO).
- `rag/risk_tiers.json` — 7 niveles elevados + `estandar` (HECHO).
- FR-08b: **un vector por documento** para 1.264 términos; **única excepción** `huesos-en-general.md` → split por sección (~9 chunks).

## Pasos

1. Implementar `especialista/index.py` (ejecutable como `python -m index`):
   a. Leer todos los `data/*.md` → `{title, slug, letter, body}`.
   b. Aplicar aliases (FR-08a): los 55 de redirección pura **no reciben vector**; resolver destino colapsando cadenas y neutralizando ciclos (casos reales del corpus); solo match exacto o prefijo único sobre título normalizado + los 9 destinos del mapa curado; los 3 huérfanos quedan `target_slug: null`.
   c. Vectorizar: 1.264 documentos completos + `huesos-en-general.md` partido por sección (~9 chunks; cada chunk identificable por su sub-término; los alias que apuntan a él — `osteoporosis`, `fractura`, `dislocación` — deben resolverse al chunk correcto).
   d. Embeddings `bge-m3` vía Ollama (`EMBED_MODEL=bge-m3`); **cachear** por hash de texto para idempotencia y re-costo.
   e. FAISS `IndexFlatIP` con normalización L2 (= coseno sobre 1024 dims). Escribir `data/index/diccionario.index`.
   f. `data/index/bm25.pkl`: `rank_bm25` sobre título + cuerpo + índice separado de títulos normalizados (con alias).
   g. `data/index/meta.json`: `faiss_id → {title, slug, letter, content, risk_tier}` + `corpus_hash` global + conteos de vectores/alias/huérfanos.
2. Crear `scripts/index.sh` (wrapper: venv + `python -m index`).
3. **Hash del corpus** (FR-11): debe cubrir contenido de `data/` **y** los artefactos de `rag/` que afectan el índice (aliases, risk_tiers) — así se detecta un índice **obsoleto**, no solo faltante.

## Salidas

- `data/index/diccionario.index`, `data/index/meta.json`, `data/index/bm25.pkl`.

## Exit criteria (gate para rag-retrieval)

- [ ] Conteo: ~1.210 vectores base + ~9 chunks (desviación justificada en heartbeat).
- [ ] Re-run idempotente: mismo `corpus_hash`, mismo número de vectores.
- [ ] Ningún faiss_id corresponde a los 55 redirect; los 3 huérfanos registrados con `target_slug: null`.
- [ ] Todo vector con `risk_tier` poblado y `meta.json` carga completo.

## Verificación

```bash
python -m index
python -c "import json;m=json.load(open('data/index/meta.json'));print(m['vector_count'], m['corpus_hash'][:12])"
python -m index   # segunda vez: hash y conteos idénticos
```

Registrar en heartbeat: conteos reales, hash del corpus, tamaño del índice.
