# Especialista en enfermedades emocionales

Agente conversacional **RAG** sobre un diccionario de 1.265 términos de enfermedades
emocionales, con **memoria persistente por usuario** y **guardarraíles médicos
deterministas**. Un único contenedor: backend FastAPI + frontend vanilla.

**Google ADK 2.x** · **FAISS + BM25** (híbrido, sin servicio de vectores) · dos perfiles
intercambiables:

| | local | nube |
|---|---|---|
| LLM | `gemma4` vía Ollama | `gemini-2.5-flash-lite` (Vertex) |
| Embeddings | `bge-m3` (1024) | `gemini-embedding-001` (3072) |
| Datos | PostgreSQL | Firestore (escala a cero) |

> **Aviso.** Ofrece una interpretación simbólica desde un diccionario de autoconocimiento.
> **No es consejo ni diagnóstico médico.** Es un proyecto académico de diplomado.

## Qué lo distingue

**La seguridad es un mecanismo, no una instrucción.** En un dominio de salud, pedirle al
modelo que derive ante una emergencia falla el día que alucina o le inyectan contexto. Aquí
nada crítico depende del LLM:

- `detect_emergency` evalúa **6 grupos de patrones deterministas antes de recuperar**. El
  test hace fallar la corrida si `retrieval.search` llega a llamarse en un caso de emergencia.
- La plantilla de derivación por nivel de riesgo la elige el **backend** a partir de los slugs
  recuperados — **156 términos** verificados de forma paramétrica.
- El **lenguaje causal está prohibido por test**: el diccionario registra asociaciones
  simbólicas, nunca «X causa Y».
- **Citación intersectada**: el modelo emite `FUENTES: slug…` y el backend descarta todo slug
  que no haya recuperado. No puede citar lo que no se le dio.

## Arquitectura

```
Contenedor único (Cloud Run en producción)
┌────────────────────────────────────────────────────┐
│ Frontend vanilla (Liquid Glass, sin build)         │
│   ↕ POST /chat (NDJSON)                            │
│ FastAPI + ADK 2.x                                  │
│   camino determinista (§9):                        │
│     injection → emergencia → extraer síntomas      │
│     → N búsquedas en paralelo → plantilla por      │
│     riesgo → 1 síntesis → citación intersectada    │
│ RAG: FAISS (bge-m3, coseno) + BM25, fusión RRF     │
│ PostgreSQL: sesiones ADK + perfiles + auditoría    │
└────────────────────────────────────────────────────┘
```

El **multi-hop es determinista**: el modelo no decide cuándo buscar. Con un modelo local el
bucle de tool-calling era poco fiable y cada iteración es una oportunidad de saltarse un
guardarraíl. `build_agent` (ADK `LlmAgent` + tools) queda como camino alternativo.

## Arranque rápido

Requisitos: Docker, y [Ollama](https://ollama.com) con `gemma4:latest` y `bge-m3:latest`.

```bash
ollama pull gemma4 && ollama pull bge-m3

scripts/index.sh     # construye el índice FAISS + BM25 en el host (necesita Ollama)
make up              # levanta app + Postgres
open http://localhost:8000
```

El índice se genera en el host y se monta en el contenedor en solo lectura: así la imagen no
necesita el corpus ni acceso a Ollama durante el build.

| Comando | Qué hace |
|---|---|
| `make up` / `make down` | levanta / apaga el stack |
| `make logs` / `make ps` | logs y estado |
| `make build` | reconstruye la imagen |
| `scripts/test.sh` | suite completa de pruebas |
| `scripts/evidence.sh` | eval e2e + capturas + GIFs + reportes |
| `scripts/secrets_audit.sh` | auditoría de secretos |
| `scripts/infra_audit.sh` | plan de Terraform + 17 aserciones de seguridad de infra |

## API

| Endpoint | Descripción |
|---|---|
| `POST /api/register` | Crea cuenta → `{token, email, profile}` |
| `POST /api/login` | Autentica → `{token, email, profile}` |
| `POST /chat` | Streaming NDJSON (Bearer). Último evento: `{session_id, kind, done, text, risk_tier, sources:[{title, slug}]}` |
| `GET /profile` | Perfil del portador del token |
| `DELETE /profile/consultations` | Borra su historial |
| `GET /sessions` | Sus sesiones ADK |
| `GET /health` | Liveness |
| `/` | Frontend |

Todo endpoint de datos exige `Authorization: Bearer`. La superficie pública se reduce a
register, login, health y el estático.

## Resultados

Eval end-to-end de **52 preguntas** por el pipeline real del chat, con verificación
**determinista** (el slug esperado está en `sources[]`, o el título del término en el texto) —
sin LLM-as-judge. Métricas por bootstrap con seed fijo.

| Métrica | Valor | IC95% |
|---|---|---|
| Global | **0.865** | [0.769, 0.942] |
| Recall single (n=31) | **0.903** | [0.806, 1.000] |
| Recall alias (n=15) | **1.000** | [1.000, 1.000] |
| Recall multi (n=6) | 0.333 | [0.000, 0.667] |
| Precisión fuera de dominio | **1.000** | 13/13 |

`gemma4` no es determinista: entre corridas se ha observado 0.865–0.885 global. Lo
reproducible es el procedimiento, no la cifra.

**Con Vertex las cifras son las mejores del proyecto:**

| Métrica | local (gemma4) | producción (Vertex) |
|---|---|---|
| Global | 0.865 | **0.923** |
| single | 0.903 | **0.935** |
| alias | 1.000 | 1.000 |
| multi | 0.333 | **0.667** |
| Latencia | 8,5 s | **2,1 s** |

La recuperación también **cierra el gate duro de M2**: alias sube de 0.867 a 0.933 (≥0.90 por
primera vez), manteniendo precisión fuera de dominio 1.0. Dos cosas hicieron falta y ninguna
era obvia: recalibrar el umbral de cobertura (estaba fijado para el espacio de `bge-m3`) y
corregir que flash-lite envuelve el JSON de extracción en un bloque markdown, lo que tenía el
multi-hop degradado en silencio. Detalle en [`docs/migration.md`](docs/migration.md) §4 y §7.

**Dos cosas honestas sobre estos números:**

1. **La precisión fuera de dominio de 1.0 se compró a costa de recall.** La cobertura se
   decide por match nominal de título/alias, no por similitud densa: en un diccionario, el
   título es la señal fiable y la prosa emocional de dos términos distintos es casi idéntica.
   El precio son 8 fallos de sinonimia coloquial (*panza→estómago*, *dormir→insomnio*)
   ausentes de `aliases.json`. En salud, inventar una interpretación es peor que admitir que
   no hay cobertura.
2. **Multi-hop es el punto débil real** (0.333 local, 0.667 en producción). Citar *todos* los
   síntomas en una síntesis cohesiva es lo más difícil, y arrastra el mismo hueco de sinonimia.

Detalle: [`docs/QA_report.md`](docs/QA_report.md) · razonamiento de diseño:
[`docs/QA_reasoning.md`](docs/QA_reasoning.md) · reporte formal: `outputs/reporte.pdf`.

## Evidencia

`scripts/evidence.sh` encadena eval → capturas → GIFs → reportes. **Cada captura se
autocomprueba**: si los chips de fuentes no se ven *en el viewport*, si falta la clase de
emergencia o si un GIF no tiene transiciones reales, la corrida **falla** en vez de producir
un PNG bonito que no prueba nada.

| Escenario | Verifica |
|---|---|
| ![registro](outputs/gifs/registro.gif) | Alta de usuario y entrada al chat |
| ![consulta](outputs/gifs/consulta.gif) | Respuesta con chips de fuentes y disclaimer |
| ![emergencia](outputs/gifs/emergencia.gif) | Derivación determinista, sin pasar por el LLM |
| ![seguridad](outputs/gifs/seguridad.gif) | Prompt injection bloqueado con 403 |
| ![memoria](outputs/gifs/memoria.gif) | Historial persistido y consultable |

Esa propiedad ya pagó: al regenerar la evidencia sobre la UI actual, las aserciones
destaparon tres defectos reales del frontend que la versión anterior de las capturas no
habría mostrado.

## Pruebas

```bash
scripts/test.sh     # 244 passed, 7 skipped
```

Los 7 saltados son los de `tests/test_auth.py` que necesitan Postgres alcanzable desde el
host (el Postgres del compose no publica puerto). Cubren el aislamiento entre usuarios, la
persistencia y el borrado del historial; para ejecutarlos hace falta un Postgres local.

Lo que la suite garantiza, más allá del conteo:

- **173 tests de seguridad médica**: los 156 términos de riesgo elevado, cada uno con su
  plantilla de derivación; 0 patrones causales en las 8 plantillas; los 6 grupos de emergencia
  con `retrieval.search` monkeypatcheado para **fallar si se llama**.
- **18 tests del backend de nube**: aislamiento entre portadores en Firestore, orden de los
  turnos en el session service, y que **a BigQuery no llegue nunca el texto de un chat**.
- **17 aserciones de seguridad de infraestructura** sobre el `terraform plan` resuelto —
  validadas por mutación (inyectar `roles/owner` o un campo de texto libre en BigQuery hace
  fallar la corrida).

## En producción

**Vivo en https://emociones-app-zxzgilzqfq-uc.a.run.app** — 37 recursos aplicados con
Terraform en GCP.

Cloud Run escalando a cero · Firestore · Vertex (`gemini-2.5-flash-lite` +
`gemini-embedding-001`) · BigQuery para analítica · **sin Cloud SQL, sin VPC Connector, sin
servicio de vectores**: el índice FAISS va horneado en la imagen.

Piso de costo real: **USD 0.12/mes** con cero uso (la imagen quedó en 147 MB comprimidos,
bajo el free tier de Artifact Registry); ~$0.38 con 500 turnos.

Verificado contra el servicio vivo: RAG con Vertex, los tres guardarraíles, memoria en
Firestore, aislamiento entre portadores y analítica en BigQuery. Un dato que salió solo de la
telemetría: **una emergencia se resuelve en 57 ms frente a 1.799 ms de una consulta normal** —
la diferencia es exactamente la recuperación y el LLM que el guardarraíl se salta.

- [`docs/presupuesto-gcp.md`](docs/presupuesto-gcp.md) — presupuesto con precios consultados y
  consumo medido, y las alternativas que se descartaron.
- [`docs/migration.md`](docs/migration.md) — arquitectura, seguridad de la infra y **lo que
  falta antes de un `apply` útil** (la app todavía habla Postgres y Ollama).

## Estructura

```
especialista/      paquete: agent, retrieval, index, medical_safety, memory, auth, guardrails
backend/main.py    FastAPI: auth, chat NDJSON, perfil, sesiones
frontend/          HTML+CSS+JS vanilla, sin build
rag/               aliases.json, risk_tiers.json, emergency_patterns.json
data/              corpus (1.265 .md) e índice generado
eval/              gold set, preguntas del e2e, eval de recuperación
scripts/           index, test, evidence, gifs, reportes, auditorías
infra/terraform/   IaC de GCP (ver docs/migration.md)
harness/           arnés de desarrollo: HARNESS.md, skills y heartbeat.md
docs/              QA_report, QA_reasoning, migration, presupuesto-gcp
```

`harness/heartbeat.md` es la bitácora del proyecto: qué se hizo, con qué evidencia y qué
deuda quedó abierta.

## Deuda abierta, declarada

- **Sinonimia coloquial** fuera de `aliases.json` (congelado). Cerrarla pide un
  `rag/synonyms.json` aparte.
- **Multi-hop 0.333** — misma causa raíz vista desde la capa de generación.
- **M9**: falta construir y subir la imagen al Artifact Registry, y el `apply` (que requiere
  visto bueno). El emulador de Firestore no se usa en local: los tests del backend de nube
  usan un doble en memoria, así que un `apply` real sería la primera vez que el código habla
  con Firestore de verdad.
