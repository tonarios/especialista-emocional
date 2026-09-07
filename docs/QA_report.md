# QA Report — Especialista en enfermedades emocionales

> Generado por `scripts/qa_report.py` a partir de la corrida real del
> 2026-09-06. Todas las cifras provienen de `outputs/evidence/e2e_results.json`;
> ninguna está escrita a mano.

## 1. Objetivo y alcance

Verificar de extremo a extremo que el **especialista en enfermedades emocionales**
(Google ADK 2.x + `gemma4` local vía Ollama, RAG híbrido sobre un diccionario de
1.265 términos) **recupera el término correcto**, **cita solo lo que recuperó**,
**deriva ante riesgo o emergencia** y **recuerda** al portador entre turnos.

Dominio evaluado: **diccionario de enfermedades emocionales** (1.216 vectores,
156 términos en niveles de riesgo elevados, 6 grupos de emergencia).

## 2. Flujo de prueba (reproducible paso a paso)

```bash
make up                       # app + Postgres (contenedor non-root)
scripts/index.sh              # índice FAISS + BM25 (en host, necesita Ollama)
scripts/evidence.sh           # eval e2e -> capturas -> GIFs -> reportes
```

`scripts/evidence.sh` encadena:

1. `scripts/e2e.py` — corre las 52 preguntas de `eval/questions.json` por el
   **pipeline real del chat** (`run_deterministic` → `gemma4`) y verifica de forma
   **determinista** (slug esperado en `sources[]`, o título del término en el texto).
   Métricas con **bootstrap seed=42, 2000 remuestreos**.
2. `scripts/capture_evidence.py` — recorre 5 escenarios sobre la **UI real** con Chrome
   headless (CDP), guardando frames y stills.
3. `scripts/gifs.py` — ensambla los frames en GIFs animados (Pillow, sin `ffmpeg`).
4. `scripts/qa_report.py` + `scripts/report.py` — este documento y el PDF.

## 3. Escenarios end-to-end sobre la UI final

Ejecutados contra la app en contenedor, con un usuario **registrado en la corrida**
(`evidencia-83308086@demo.co`) — no hay datos precargados ni mocks.

| Escenario | FR/NFR | Qué demuestra | Resultado |
|---|---|---|---|
| registro | FR-16 / FR-18 | Alta de usuario y entrada al chat (UI Liquid Glass) | ✓ |
| consulta | FR-03 / FR-19 | Respuesta con chips de fuentes y disclaimer visible | ✓ |
| emergencia | FR-06 | Derivación determinista: no pasa por el LLM | ✓ |
| seguridad | NFR-01 | Prompt injection bloqueado con 403 | ✓ |
| memoria | FR-13 / FR-14 | Historial persistido, consultable y borrable | ✓ |

Cada escenario **falla la corrida** si su aserción no se cumple (chips presentes,
clase `.message.emergency` aplicada, texto de bloqueo, chat visible tras el registro).

## 4. Tablas de resultados (corrida real contra el LLM)

> No se asume acierto: cada veredicto queda auditable en
> `outputs/evidence/e2e_results.json` (consulta, esperado, citas devueltas y latencia).

### 4.1 Desempeño global

| Media | Mediana | Desv. est. | IC95% bootstrap | n |
|---|---|---|---|---|
| 0.865 | 1.000 | 0.341 | [0.769, 0.942] | 52 |

> **Variabilidad real entre corridas:** `gemma4` no es determinista, así que la cifra se mueve
> entre ejecuciones (se han observado global 0.865–0.885 y single 0.903–0.935 sobre el mismo
> índice y el mismo gold set). Lo que **sí** es reproducible es el procedimiento: mismo
> `questions.json`, misma verificación determinista y mismo bootstrap (seed=42).
> Las cifras de esta tabla son las de la última corrida de `scripts/evidence.sh`.

### 4.2 Por tipo de consulta

| Tipo | n | Recall | Mediana | Desv. est. | IC95% bootstrap | Latencia media |
|---|---|---|---|---|---|---|
| single | 31 | 0.903 | 1.000 | 0.296 | [0.806, 1.000] | 8.46 s |
| alias | 15 | 1.000 | 1.000 | 0.000 | [1.000, 1.000] | 10.57 s |
| multi | 6 | 0.333 | 0.000 | 0.471 | [0.000, 0.667] | 9.68 s |

### 4.3 Recuperación aislada (§13.0)

| Tipo | Resultado | Meta | Estado |
|---|---|---|---|
| single | 27/31 (0.871) | recall@5 ≥ 0.85 | ✓ |
| alias | 13/15 (0.867) | recall@5 ≥ 0.90 | parcial |
| risk_tier | 9/10 (0.900) | término en top-k (10/10) | parcial |
| multi | 5/6 (0.833) | cada síntoma en top-k (6/6) | parcial |
| out_of_domain | 13/13 (1.000) | precision = 1.0 | ✓ |
| emergency | 5/5 (1.000) | corta antes del LLM | ✓ |

### 4.4 Fallos observados

| id | tipo | consulta | esperado | recuperado |
|---|---|---|---|---|
| g003 | single | me quedé sin voz de repente | afonia-o-extincion-de-voz, garganta-laringitis | audicion-perdida-de, voz-ronquera, cerebro-equilibrio-perdida-de-o-aturdimientos |
| g030 | single | me dan infecciones urinarias seguido | vejiga-cistitis, vejiga-dolores-de | orina-infecciones-urinarias-cistitis, infecciones-en-general, incontinencia-fecal-urinaria |
| g032 | single | se me duermen los pies | adormecimiento-torpor, pies-en-general | entumecimiento-u-hormigueo, pies-frios |
| g043 | multi | se me cae el pelo y me salen granos desde que cambié de trabajo | alopecia, piel-acne | piel-granos-acne, piel-brote-de-granos, pelo |
| g044 | multi | ando estreñido y con dolor de espalda baja | intestinos-estrenimiento, espalda-dolor-de-parte-inferior | espalda-en-general, espalda-dolor-de-parte-inferior, espalda-dolor-de-parte-central-12-vertebras-dorsales |
| g045 | multi | me duelen las rodillas, tengo várices y siempre estoy cansada | rodillas-dolores-de, sangre-varices, agotamiento-o-burnout | rodillas-dolores-de, piernas-varices, cansancio-fatiga-en-general |
| g046 | multi | acidez, colitis y ansiedad al mismo tiempo | estomago-acidez-ardores-pirosis, intestinos-colitis-mucosidad-del-colon, ansiedad | estomago-acidez-ardores-pirosis, intestinos-colitis-mucosidad-del-colon, ano-rectocolitis-colitis-ulcerosa-dolores-anales |

## 5. Seguridad médica y del sistema

- **FR-05a (derivación por riesgo):** 156 términos en 7 niveles elevados → plantilla de
  derivación resuelta **en el backend**, no por prompt. Test paramétrico sobre los 156.
- **FR-05b (lenguaje causal):** 0 patrones causales en las 8 plantillas ni en las
  respuestas de emergencia / sin cobertura. El registro es **asociativo, nunca causal**.
- **FR-06 (emergencias):** 6 grupos en `rag/emergency_patterns.json` cortan **antes** de
  recuperar; el test hace fallar la corrida si `retrieval.search` llega a llamarse.
- **NFR-01 (injection):** patrones de inyección y de dominio (prescripción, diagnóstico
  forzado) → 403 + `audit_log`, sin llegar al LLM.
- **FR-17 (aislamiento):** `user_id` = email autenticado; `/chat`, `/profile` y `/sessions`
  exigen `Bearer` y devuelven solo datos del portador.
- **NFR-07:** nunca se loguea contenido de chats; el historial es borrable por el usuario
  (FR-14b, `DELETE /profile/consultations`).

## 6. Evidencia de la memoria persistente

Capturas del **sistema final**, con el token real del usuario registrado en esta corrida.

### Perfil del portador (`GET /profile`)

![Perfil del portador](../outputs/evidence/profiles.png)

### Sesiones ADK persistidas (`GET /sessions`)

![Sesiones ADK](../outputs/evidence/sessions.png)

### El agente responde desde el historial (FR-13)

![Pregunta de memoria](../outputs/evidence/memoria.png)

## 7. GIFs de las pruebas E2E (Chrome CDP)

> Capturados sobre la **UI final Liquid Glass** con Chrome headless vía CDP
> (`scripts/capture_evidence.py`) y ensamblados con Pillow (`scripts/gifs.py`).

### registro — FR-16 / FR-18

Alta de usuario y entrada al chat (UI Liquid Glass) (25 frames).

![registro](../outputs/gifs/registro.gif)

### consulta — FR-03 / FR-19

Respuesta con chips de fuentes y disclaimer visible (22 frames).

![consulta](../outputs/gifs/consulta.gif)

### emergencia — FR-06

Derivación determinista: no pasa por el LLM (23 frames).

![emergencia](../outputs/gifs/emergencia.gif)

### seguridad — NFR-01

Prompt injection bloqueado con 403 (23 frames).

![seguridad](../outputs/gifs/seguridad.gif)

### memoria — FR-13 / FR-14

Historial persistido, consultable y borrable (30 frames).

![memoria](../outputs/gifs/memoria.gif)


## 8. Conclusión

El sistema es **reproducible** (índice idempotente por hash de corpus, eval con seed fijo),
**seguro por mecanismo** (emergencias y derivación resueltas en backend, no por prompt) y
tiene **memoria persistente** por portador (sesiones ADK + `profiles.consultations` en
Postgres). Su precisión end-to-end verificada contra el LLM real es
**0.865** (IC95% [0.769, 0.942], n=52).

El punto débil sigue siendo **multi-hop**: citar *todos* los síntomas en una síntesis
cohesiva con un modelo local, agravado por la sinonimia coloquial ausente de
`aliases.json`. Se priorizó deliberadamente la **precisión fuera de dominio = 1.0**:
en un dominio de salud un falso positivo es peor que un fallo de recall.

Artefactos generados:

| Artefacto | Ruta |
|---|---|
| Este reporte | `docs/QA_report.md` |
| Razonamiento de diseño | `docs/QA_reasoning.md` |
| Reporte formal | `../outputs/reporte.pdf` |
| Resultados crudos del eval | `../outputs/evidence/e2e_results.json` |
| GIFs de escenarios | `../outputs/gifs/*.gif` |
| Stills de evidencia | `../outputs/evidence/*.png` |
| Auditoría de secretos | `../outputs/evidence/secrets_audit.txt` |
