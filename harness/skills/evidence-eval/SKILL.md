---
name: evidence-eval
description: Evidencia de registro/memoria/RAG (capturas autocomprobadas), eval end-to-end vía CDP contra gemma4 (verificación determinista + métricas con bootstrap y seed fijo), reportes Markdown + HTML→PDF y GIFs de escenarios (Pillow, sin ffmpeg). M8 — EL entregable que se califica.
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
5. **Reporte HTML → PDF** (`scripts/report.py`, Chrome headless; no hace falta LaTeX): método, gold set, decisiones basadas en datos (k/τ/peso elegidos en `rag-retrieval`), métricas, guardarraíles médicos y riesgos/mitigaciones (§14).
6. **Reportes Markdown**: `docs/QA_report.md` **generado** desde los datos (`scripts/qa_report.py`) y `docs/QA_reasoning.md` (razonamiento de diseño, a mano).
7. **GIFs** (`scripts/gifs.py`, Pillow — el host no tiene `ffmpeg`): registro, chat RAG con chips, emergencia, injection bloqueado (403), memoria.

## Reglas de la evidencia (aprendidas al regenerarla)

- **Cada captura se autocomprueba.** Un escenario sin aserción sobre el DOM produce PNGs
  bonitos que no prueban nada. Si los chips no se ven *en el viewport*, si falta la clase
  `.message.emergency` o si el GIF no tiene transiciones reales, **la corrida falla**.
- **La UI cambia; la evidencia caduca.** Regenerar tras cualquier cambio de frontend o del
  pipeline (`run_deterministic`), y reconstruir la imagen antes de capturar: el frontend va
  dentro del contenedor.
- **Chrome cachea.** El perfil de CDP es persistente: `Network.setCacheDisabled` o se captura
  el frontend anterior. `localStorage` es por origen: limpiarlo en `about:blank` no borra nada.
- **Nada hardcodeado en los reportes.** Los KPIs se leen de `e2e_results.json`.

## Salidas

- `outputs/evidence/*.png` (8 stills), `outputs/gifs/*.gif` (5), `outputs/reporte.pdf`,
  `docs/QA_report.md`, `docs/QA_reasoning.md`.
- Los **frames** intermedios (`outputs/gifs/frames/`) son regenerables y van al `.gitignore`;
  los artefactos finales **sí** se commitean (los enlaza `docs/QA_report.md`).

## Exit criteria (M8)

- [ ] Los stills existen y muestran datos reales (usuario creado en la corrida, consultas persistidas, chips visibles).
- [ ] Los 5 GIFs se generan y cada uno tiene transiciones reales.
- [ ] El e2e corre completo; métricas con seed fijo reportadas; aciertos consistentes con las metas del PRD.
- [ ] PDF compila y contiene: método, decisiones con datos (k/τ/peso), métricas y el tratamiento del riesgo médico (FR-05a/b, FR-06).
- [ ] `docs/QA_report.md` se genera desde los datos y sus enlaces resuelven en el repo.

## Verificación

```bash
make up && scripts/evidence.sh    # e2e + capturas + GIFs + QA_report.md + PDF
ls outputs/evidence/ outputs/gifs/ outputs/reporte.pdf docs/QA_report.md
```

Registrar en heartbeat: métricas finales (media/mediana/DE/IC95%), archivos generados y confirmación de que el reporte compila.
