# Razonamiento — Especialista en enfermedades emocionales

Documento hermano de [`QA_report.md`](QA_report.md): allí están los **números** de la
corrida; aquí, **por qué** el sistema está construido así. Las decisiones se toman contra
`PRD.md`; cuando hubo fricción, gana el PRD y queda registrada en `harness/heartbeat.md`.

## 1. Decisión central: la seguridad es un mecanismo, no una instrucción

El dominio es salud. Un prompt que *pide* al modelo derivar ante una emergencia falla el día
que el modelo alucina, se le inyecta contexto o simplemente ignora la instrucción. Por eso
(NFR-02b) **nada crítico depende del LLM**:

- `detect_emergency` evalúa 6 grupos de patrones deterministas **antes** de recuperar. El test
  hace fallar la corrida si `retrieval.search` llega a llamarse en un caso de emergencia.
- La plantilla de derivación por `risk_tier` la elige el **backend** a partir de los slugs
  recuperados, no el modelo. 156 términos elevados, verificados de forma paramétrica.
- El **lenguaje causal** está prohibido por test sobre las plantillas: el diccionario registra
  asociaciones simbólicas, nunca «X causa Y» (FR-05b).
- La inyección de prompt corta con 403 y queda en `audit_log` sin llegar al LLM (NFR-01).

Consecuencia práctica: los guardarraíles se pueden probar sin invocar al modelo, y su
comportamiento no cambia entre corridas.

## 2. Recuperación: el diccionario da una señal nominal fiable

El corpus son 1.265 términos de un diccionario. Su título y sus alias **son** la señal fuerte;
la prosa emocional de dos términos distintos es casi idéntica (FR-09), así que el denso solo
no discrimina. De ahí el diseño:

- **Cobertura** = existe match nominal normalizado de título/alias (con *light stemming* de
  plurales y deverbales, más stopwords). Ese match es el umbral τ de FR-09b.
- **Ranking** = RRF sobre denso (`bge-m3`, FAISS `IndexFlatIP` con vectores L2-normalizados,
  es decir coseno) + BM25 con peso reforzado al match de título/alias.
- **El denso solo desempata** dentro del mismo nivel de match.

Esto compra **precision 1.0 fuera de dominio** a costa de recall en sinonimia coloquial. Es un
intercambio deliberado: en salud, inventar una interpretación para «panza» es peor que admitir
que no hay cobertura. La deuda está cuantificada en `QA_report.md` §4.3-4.4.

## 3. Multi-hop determinista en vez de tool-calling iterativo

El camino por defecto (§9) no deja que el modelo decida cuándo buscar:

```
check_prompt_injection → detect_emergency → extract_symptoms (1 llamada estructurada)
  → N retrieval.search en paralelo → plantilla por risk_tier (backend) → 1 síntesis
  → citación intersectada → audit
```

El tool-calling de ADK (`build_agent`) queda como camino alternativo. Motivo: con un modelo
local el bucle de tools era poco fiable y no acotado, y cada iteración es una oportunidad de
saltarse un guardarraíl. El pipeline fijo es auditable y su coste es predecible.

**Citación intersectada:** el modelo emite `FUENTES: slug…` y el backend **descarta todo slug
que no haya recuperado**. El modelo no puede citar lo que no se le dio.

## 4. Hallazgo de entorno: `gemma4` es un modelo *thinking*

Con rol `system`, o sin `think:false`, Ollama devuelve `content=''`: los tokens se van al
razonamiento. Además `LiteLlm 1.100 + ollama_chat/gemma4` devolvía `content=''` de forma no
determinista. Por eso el camino determinista **no usa LiteLlm**: llama al endpoint nativo
`/api/chat` con `think:false` vía `httpx`, el mismo patrón que `index.py` usa para embeddings.

## 5. Memoria: dos capas distintas

1. **Sesiones ADK** (FR-12) — `DatabaseSessionService` sobre Postgres: la conversación
   sobrevive a `make down && make up`.
2. **Perfil del portador** (FR-13/FR-14) — `profiles.consultations` guarda
   `[{symptom, term, ts}]` por usuario.

El camino determinista **inyecta el historial en la síntesis en cada turno** y detecta
preguntas de memoria («¿cuál fue mi última consulta?»), respondiéndolas desde el historial
persistido. `DELETE /profile/consultations` borra solo lo del portador (FR-14b).

**Aislamiento (FR-17):** el `user_id` es el email autenticado del token; `/chat`, `/profile` y
`/sessions` exigen `Bearer` y solo devuelven datos del portador. Verificado con un test en que
el usuario A no ve nada de B.

## 6. Cómo se produce la evidencia (y por qué se puede creer)

`scripts/evidence.sh` encadena eval → capturas → GIFs → reportes. Dos propiedades importan:

- **Verificación determinista, no LLM-as-judge.** Una respuesta acierta si el slug esperado
  está en `sources[]` o el título del término aparece en el texto. Sin juicios subjetivos en
  runtime; el veredicto de cada pregunta queda en `outputs/evidence/e2e_results.json`.
- **Las capturas se autocomprueban.** Cada escenario lleva aserciones sobre el DOM real
  (chips visibles *en el viewport*, clase `.message.emergency` aplicada, texto de bloqueo,
  chat visible tras el registro). Una captura que no prueba lo que dice probar **rompe la
  corrida** en vez de producir un PNG bonito y vacío.

Esa segunda propiedad ya pagó: al reconstruir la evidencia sobre la UI Liquid Glass, las
aserciones destaparon tres defectos reales del frontend que la versión anterior de las
capturas no habría mostrado (resaltado de emergencia perdido en el refactor a NDJSON, el
detalle técnico del guardarraíl expuesto al usuario, y los chips de fuentes fuera de vista).

**Métricas:** media, mediana, desviación estándar e **IC 95% por bootstrap** (seed=42, 2.000
remuestreos) — sin asumir normalidad, y reproducible.

**GIFs sin `ffmpeg`:** el host no lo tiene, así que `scripts/gifs.py` ensambla con Pillow. Para
que pesen lo razonable se congela la animación del fondo durante la captura y se usa una
**paleta única** por escenario (si cada frame lleva su paleta, se pierde la compresión delta y
el GIF pesa ~10x).

## 7. Deuda abierta, declarada

- **Sinonimia coloquial** ausente de `aliases.json` (M0 está congelado). Cerrarla pide un
  `rag/synonyms.json` aparte, no tocar el fichero congelado.
- **Multi-hop 0.333**: el modelo local no cita *todos* los síntomas en una síntesis cohesiva.
  Es la misma causa raíz vista desde la capa de generación.
- **M9 (`gcp-terraform`)** sigue pendiente: `infra/terraform/` es todavía la copia del repo base.
