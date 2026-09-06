---
name: rag-retrieval
description: Recuperación híbrida RRF (FAISS coseno + BM25 con título/alias reforzado), resolución de alias, umbral τ con respuesta de sin cobertura, presupuesto de tokens (800/4.000) y sintonización de k/τ/peso CON el gold set. GATE DURO de M2.
---

# rag-retrieval — M2b: fusión híbrida + τ fijado con datos

## Cuándo activar

- Después de `rag-index` (requiere índice construido).

## Entradas

- `data/index/*`, `eval/gold_set.json` (80 casos), `rag/aliases.json`.
- FR-09 (fusión RRF denso+léxico con match normalizado de título/alias con peso reforzado), FR-09b (τ → "sin cobertura", no resultados de relleno), FR-10/10b (contexto delimitado; 800 tok/doc, 4.000/turno, corte por párrafo, título siempre preservado).

## Pasos

1. Implementar `especialista/retrieval.py`:
   - `search(query, k=5)`: RRF de (a) coseno FAISS bge-m3 y (b) BM25 título+cuerpo, con **match normalizado de título/alias con peso reforzado** (la señal fiable de un diccionario).
   - Resolver alias **antes** de devolver (FR-08a): nunca devolver un stub de redirección.
   - Puntaje fusionado por documento; si el mejor < **τ** → señal explícita de **SIN COBERTURA** (FR-09b).
   - Recorte a presupuesto (FR-10b): ≤800 tokens/doc, ≤4.000/turno, cortando por **párrafo completo**, preservando siempre el título.
   - `format_for_llm(results)`: contexto **delimitado y etiquetado** por documento (FR-10).
2. Implementar `eval/retrieval.py` (`python -m eval.retrieval --k K`): corre los 80 casos del gold set **sin LLM** — determinista y rápido; reporta recall@k por tipo (`single`, `alias`, `multi`), precisión en `out_of_domain`, y cobertura `risk_tier`.
3. **Sintonizar con datos, no intuición**: barrido pequeño de k ∈ {3,5,6,8}, τ y peso de fusión hasta cumplir las metas. Fijar los valores elegidos como defaults comentados en `retrieval.py` y documentarlos en heartbeat (k, τ, peso, métricas obtenidas).

## Salidas

- `especialista/retrieval.py`, `eval/retrieval.py`, valores k/τ/peso fijados y documentados.

## Exit criteria (GATE DURO M2 — no cerrar la skill sin cumplirlos)

- [ ] `recall@k ≥ 0.85` en `single` (31 casos).
- [ ] `recall@k ≥ 0.90` en `alias` (15 casos).
- [ ] `precision = 1.0` en `out_of_domain` (13 casos) — **cero falsos positivos**; incluye `osteomielitis`, `empiema`, `irritabilidad`, `sudoración` → SIN COBERTURA, sin stub.
- [ ] En `multi` (6 casos): cada síntoma del caso aparece en el top-k.
- [ ] En `risk_tier` (10 casos): el término esperado queda en top-k (permitirá la plantilla de derivación en `agent-core`).
- [ ] En `emergency` (5 casos): documentar que la capa de recuperación **no debe** llegar a ejecutarse (corta `detect_emergency` antes).

## Verificación

```bash
python -m eval.retrieval --k 5
```

Copiar el reporte de métricas por tipo al heartbeat (decisión k/τ/peso + valores obtenidos).
