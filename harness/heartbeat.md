# heartbeat — estado del proceso (ah-emociones)

Última actualización: 2026-09-05
LLM activo: ND (arnés entregado, sin skills ejecutadas)

## Resumen por skill

| # | Skill | Estado | Milestone | Gate | Fecha | LLM | Evidencia |
|---|-------|--------|-----------|------|-------|-----|-----------|
| 1 | bootstrap | pending | M1 | — | — | — | — |
| 2 | medical-safety | pending | transversal | — | — | — | — |
| 3 | rag-index | pending | M2 | — | — | — | — |
| 4 | rag-retrieval | pending | M2 | GATE DURO gold set | — | — | — |
| 5 | agent-core | pending | M3 | — | — | — | — |
| 6 | auth-memory | pending | M4 | — | — | — | — |
| 7 | frontend | pending | M5 | — | — | — | — |
| 8 | docker | pending | M6 | — | — | — | — |
| 9 | security-tests | pending | M7 | — | — | — | — |
| 10 | evidence-eval | pending | M8 | — | — | — | — |
| 11 | gcp-terraform | pending | M9 | — | — | — | — |

## Bitácora (cronológica)

- **2026-09-05 — PREPARACIÓN.** PRD analizado a fondo; arnés de desarrollo generado: `HARNESS.md` + 11 skills + este `heartbeat.md`. Estado del repo al arrancar: **M0 PARCIAL** — hechos `rag/aliases.json`, `rag/risk_tiers.json`, `eval/gold_set.json`, `scripts/build_aliases.py`, `scripts/build_risk_tiers.py`; **pendiente** `rag/emergency_patterns.json` (lo crea la skill `medical-safety`). El sistema aún no existe: la primera skill a ejecutar es `bootstrap`.
