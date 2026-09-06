---
name: agent-core
description: Agente ADK 2.x con gemma4 vía LiteLlm: instrucción de sistema en español, tools search_dictionary/get_user_profile/record_consultation, multi-hop DETERMINISTA por defecto, plantillas por risk_tier resueltas en backend y citaciones intersectadas. FR-01..07, §9.
---

# agent-core — M3: agente de dominio

## Cuándo activar

- Después de cerrar el gate de M2 (`rag-retrieval`). `auth-memory` implementará los stubs de perfil; esta skill **contrata su interfaz**.

## Entradas

- `especialista/retrieval.py`, `especialista/medical_safety.py`, `rag/emergency_patterns.json`.
- ADK 2.x (`LlmAgent`) + LiteLlm `ollama/gemma4:latest`.
- PRD FR-01/02/03/04/05/07 y §9 (multi-hop **determinista** por defecto; el tool-calling iterativo del LLM queda como camino alternativo, nunca el default).

## Pasos

1. **Instrucción de sistema** completa (esqueleto mínimo, en español):
   - Rol: especialista en **significados emocionales** de síntomas (no médico).
   - Obligatorio: recuperar con `search_dictionary` antes de responder y **citar** los términos usados.
   - Relacionar varios síntomas cuando el usuario los menciona.
   - Usar la **plantilla provista por el backend** según `risk_tier`; registrar siempre en modo **asociativo**, nunca causal (FR-05b).
   - Si `search_dictionary` devuelve SIN COBERTURA: decirlo, **no** rellenar con interpretación; fuera de dominio: reencauzar cortésmente (FR-07).
   - Español, tono cálido y claro; no inventar términos fuera del diccionario.
2. **Tools (contrato)**:
   - `search_dictionary(query: str) -> str` — envuelve `retrieval.search` + `format_for_llm`, incluye la señal SIN COBERTURA.
   - `get_user_profile() -> str` — stub hasta `auth-memory` (devuelve el historial de consultas).
   - `record_consultation(symptoms: list[str], terms: list[str]) -> str` — no-op hasta `auth-memory`.
3. **Multi-hop determinista** (FR-04, §9): extraer síntomas con UNA llamada de salida estructurada → N recuperaciones **en paralelo** → UNA síntesis. Razón del PRD: con gemma4 local el tool-calling iterativo es la variable menos controlable; este camino es testeable en pytest sin depender del modelo.
4. **Orquestación del turno en backend** (NFR-02b): `detect_emergency` ANTES de recuperar → plantilla de escalamiento; `check_prompt_injection` antes del LLM; si el top-1 es de nivel elevado → seleccionar la plantilla de derivación por `risk_tier` y entregársela al modelo. **El backend elige la plantilla, no el prompt.**
5. **Citación intersectada** (§9): el modelo emite los slugs **usados**; el backend los **intersecta** con lo recuperado para emitir `sources[]`. Nunca reportar "recuperados" como "usados".

## Salidas

- `especialista/agent.py` (construcción del `LlmAgent` + runner ADK), `especialista/system_instruction.py` (o `.md` versionado), contrato de tools documentado.

## Exit criteria (M3)

- [ ] Smoke con gemma4: "me duele la garganta a menudo" → respuesta cita el término recuperado y lleva disclaimer.
- [ ] "me duele la garganta y no puedo dormir" → relaciona ambos términos (multi-hop determinista).
- [ ] Emergencia e injection **no llegan al LLM** (corte determinista backend, verificado con audit log).
- [ ] Fuera de dominio ("qué acciones comprar hoy") → reencauza, sin confabular términos.
- [ ] Hueco conocido (ej. "sudoración") → declara SIN COBERTURA.

## Verificación

- Script smoke local (p. ej. `scripts/smoke_agent.sh`) con los 5 casos anteriores contra el runner; copiar los resultados al heartbeat.
