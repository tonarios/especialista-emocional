---
name: evidence-eval
description: Evidencia de registro/memoria/RAG (capturas), eval end-to-end con chrome-devtools contra gemma4 (verificación determinista + métricas con bootstrap y seed fijo), reporte LaTeX→PDF y GIFs de escenarios. M8 — EL entregable que se califica.
---

# evidence-eval — M8: evidencia, eval e2e y reporte (imprescindible)

## Cuándo activar

- Después de `security-tests` (todo en verde). Usa el sistema completo con gemma4.

## Entradas

- PRD §13 puntos 3 y 4, D8, O8; `eval/gold_set.json`; `questions.json` (se genera aquí) para el e2e.

## Pasos

1. `questions.json`: preguntas del dominio + término esperado, derivadas del gold set (`single`/`alias`/`multi`), validadas contra el corpus.
2. **Evidencia de registro y memoria** (SQL/endpoints + capturas): `outputs/evidence/register.png`, `profiles.png`, `sessions.png`, `rag_sources.png` (respuesta RAG con chips de fuentes visibles).
3. **Eval e2e** (chrome-devtools o script de browser): cada pregunta → respuesta de gemma4 a través del chat → **verificación determinista** (la respuesta cita/contiene el término esperado; o SIN COBERTURA donde corresponda) → registrar aciertos y tiempos.
4. **Métricas**: media/mediana/DE/IC95% por **bootstrap con seed fijo** (reproducible). Script `scripts/evidence.sh`.
5. **Reporte LaTeX → PDF**: método, gold set, decisiones basadas en datos (k/τ/peso elegidos en `rag-retrieval`), métricas, guardarraíles médicos y riesgos/mitigaciones (§14).
6. **GIFs** (`scripts/gifs.sh`): registro+login, chat RAG con chips, multi-hop, emergencia, injection bloqueado (403).

## Salidas

- `outputs/evidence/*.png`, `outputs/*.gif`, `outputs/reporte.pdf` + fuentes LaTeX versionadas.

## Exit criteria (M8)

- [ ] Las 4 capturas existen y muestran datos reales (usuarios creados, consultas persistidas, chips).
- [ ] El e2e corre completo; métricas con seed fijo reportadas; aciertos consistentes con las metas del PRD.
- [ ] PDF compila y contiene: método, decisiones con datos (k/τ/peso), métricas y el tratamiento del riesgo médico (FR-05a/b, FR-06).

## Verificación

```bash
scripts/evidence.sh    # capturas + métricas + PDF
scripts/gifs.sh
ls outputs/evidence/ outputs/*.pdf outputs/*.gif
```

Registrar en heartbeat: métricas finales (media/mediana/DE/IC95%), archivos generados y confirmación de que el reporte compila.
