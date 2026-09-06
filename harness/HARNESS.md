# HARNESS — ah-emociones (orquestador lean de desarrollo)

Orquestador de desarrollo derivado de `PRD.md`. Guía a **cualquier LLM** (Claude, opencode, Gemini CLI, etc.) para construir el sistema milestone a milestone mediante skills autocontenidas. Este arnés es de **desarrollo**; el QA/eval del PRD §13 es la skill `evidence-eval`.

## Rol del orquestador

1. **Fuente de verdad: `PRD.md`.** Nunca contradecir un FR/NFR; ante fricción gana el PRD y se registra en `heartbeat.md`.
2. Ejecutar las skills **en orden, una a la vez**, con gates explícitos.
3. Verificar **todo con comandos reales** antes de marcar `done`.
4. Mantener `harness/heartbeat.md` actualizado (antes y después de cada skill).

## Rutina (bucle invariante)

1. **LEER** `PRD.md` (si no está en contexto) y `harness/heartbeat.md` (estado real).
2. **ELEGIR** la siguiente skill `pending` cuyo gate previo esté OK (roadmap abajo).
3. **CARGAR** `harness/skills/<skill>/SKILL.md` completa.
4. **EJECUTAR** los pasos en orden; anotar decisiones en la bitácora del heartbeat.
5. **VERIFICAR** los exit criteria con los comandos de la sección "Verificación".
6. **REGISTRAR** estado de la skill, evidencia y bitácora en `heartbeat.md`.
7. **GATE**: si el gate de milestone se cumple → commit del trabajo (política del owner). Si falla → estado `failed`, registrar evidencia y **DETENERSE a reportar** (nunca encadenar skills sobre fallos).

## Catálogo y roadmap (gates marcados)

| # | Skill | Milestone | Línea | Gate para pasar |
|---|-------|-----------|-------|-----------------|
| 1 | `bootstrap` | M1 | Imprescindible | paquete importable + `/health` + línea base commiteada |
| 2 | `medical-safety` | transversal | Imprescindible | 6 grupos de emergencia + plantillas por risk_tier + causal prohibido testeable |
| 3 | `rag-index` | M2 | Imprescindible | índice reproducible con conteos esperados |
| 4 | `rag-retrieval` | M2 | Imprescindible | **GATE DURO**: recall ≥0.85 / ≥0.90 / precision 1.0 con gold set |
| 5 | `agent-core` | M3 | Imprescindible | smoke multi-hop + citas + disclaimer |
| 6 | `auth-memory` | M4 | Imprescindible | aislamiento por usuario + persistencia + delete |
| 7 | `frontend` | M5 | Imprescindible | flujo completo con chips de fuentes + disclaimer visible |
| 8 | `docker` | M6 | Deseable | `make up` + chat + persistencia + non-root |
| 9 | `security-tests` | M7 | Imprescindible | pytest verde + secrets_audit limpio |
| 10 | `evidence-eval` | M8 | Imprescindible | PNGs + PDF + GIFs con métricas |
| 11 | `gcp-terraform` | M9 | Acotado | `terraform validate/plan` válido + doc de migración |

**Línea de corte (§15):** Imprescindible = sistema + M7 + M8 (el entregable que se califica). M6 deseable; M9 acotado (plan validado; `apply` solo con visto bueno del owner).

## Reglas globales (aplican a todas las skills)

- **Idioma:** todos los artefactos (docs, prompts, UI, harness) en **español**; identificadores de código en inglés estándar.
- **Seguridad:** nunca escribir secretos en archivos; `.env` fuera de git; nunca loguear contenido de chats (NFR-07); SQL solo parametrizado (NFR-03).
- **Commits:** solo al cerrar el gate de una skill (pedido explícito del owner del proyecto), registrando el hash del commit en `heartbeat.md`.
- **Pasos marcados (hecho) en el PRD no se rehacen** (M0 parcial: `rag/aliases.json`, `rag/risk_tiers.json`, `eval/gold_set.json`, `scripts/build_*.py`).
- Cada skill cita en la bitácora del heartbeat los FR/NFR que cumple.
- Los valores numéricos (k, τ, peso de fusión) se fijan **con datos** en `rag-retrieval`; nunca a ojo.

## Constantes del dominio (fijadas)

| Constante | Valor | Ref PRD |
|---|---|---|
| Paquete Python / proyecto | `especialista` / `ah-emociones` | §17.1 |
| Repo base (copiar módulos, no modificar) | `../ah-grupo-fundador` | §18 |
| LLM local | `ollama/gemma4:latest` vía LiteLlm | D3 |
| Embeddings | `bge-m3` (Ollama, 1024 dims) | D2 |
| Motor de vectores | FAISS (`faiss-cpu`, coseno) + `rank-bm25` | D1 |
| k por defecto | 5 (fijado con gold set en `rag-retrieval`) | FR-09 |
| Umbral τ | se fija empíricamente en M2 | FR-09b |
| Presupuesto de contexto | 800 tok/doc, 4.000/turno, corte por párrafo | FR-10b |
| Corpus | 1.265 md → 1.210 vectores base + ~9 chunks | §3 |
| Términos de riesgo elevado | 156 (7 niveles) | FR-05a |
| Gold set | 80 casos (31 single / 15 alias / 13 ood / 10 risk / 6 multi / 5 emergency) | §13.0 |
| Metas de recuperación | recall@k ≥0.85 single; ≥0.90 alias; precision=1.0 ood | §13.0 |
| DB | `postgres:16-alpine` stock, sin extensiones | §11 |
| Ollama desde Docker | `http://host.docker.internal:11434` | §11 |
| Makefile | SOLO `build`/`up`/`down`/`logs`/`ps` | D9 |
| Índice | `data/index/{diccionario.index, meta.json, bm25.pkl}` | FR-08 |
| Multi-hop | determinista por defecto (extraer → N recuperaciones paralelas → 1 síntesis) | §9 |

## Preguntas abiertas a vigilar (§17)

- **17.2 / 17.3:** LLM y embeddings en GCP → resolver **antes** de `gcp-terraform apply` (D10: Gemini vía Vertex recomendado).
- **17.4:** índice baked en imagen (default propuesto) vs descargar de GCS.
- **17.5:** confirmar estabilidad de `gemma4:latest` (contexto/latencia) durante `evidence-eval`.
- **17.9:** ¿el diplomado exige despliegue vivo? Determina si M9 llega a `apply` o queda en `plan` validado.
