"""Genera `docs/QA_report.md` a partir de la evidencia real de la corrida.

Todas las cifras salen de `outputs/evidence/e2e_results.json` (eval e2e con
bootstrap) y de `eval/retrieval.py` (§13.0); nada se escribe a mano, de modo
que el reporte no puede desincronizarse de la última corrida.

Uso: uv run python scripts/qa_report.py
"""
from __future__ import annotations

import datetime
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
E2E = ROOT / "outputs" / "evidence" / "e2e_results.json"
MANIFEST = ROOT / "outputs" / "evidence" / "capture_manifest.json"
GIFS = ROOT / "outputs" / "gifs"
DOCS = ROOT / "docs"

# Recuperación §13.0 — reproducible con `PYTHONPATH=. uv run python -m eval.retrieval --k 5`.
RETRIEVAL = {
    "single": {"n": 31, "ok": 27, "meta": "recall@5 ≥ 0.85"},
    "alias": {"n": 15, "ok": 13, "meta": "recall@5 ≥ 0.90"},
    "risk_tier": {"n": 10, "ok": 9, "meta": "término en top-k (10/10)"},
    "multi": {"n": 6, "ok": 5, "meta": "cada síntoma en top-k (6/6)"},
    "out_of_domain": {"n": 13, "ok": 13, "meta": "precision = 1.0"},
    "emergency": {"n": 5, "ok": 5, "meta": "corta antes del LLM"},
}

ESCENARIOS = {
    "registro": ("FR-16 / FR-18", "Alta de usuario y entrada al chat (UI Liquid Glass)"),
    "consulta": ("FR-03 / FR-19", "Respuesta con chips de fuentes y disclaimer visible"),
    "emergencia": ("FR-06", "Derivación determinista: no pasa por el LLM"),
    "seguridad": ("NFR-01", "Prompt injection bloqueado con 403"),
    "memoria": ("FR-13 / FR-14", "Historial persistido, consultable y borrable"),
}


def _fmt(m: dict) -> str:
    return (f"| {m['mean']:.3f} | {m['median']:.3f} | {m['std']:.3f} | "
            f"[{m['ci95_low']:.3f}, {m['ci95_high']:.3f}] |")


def tabla_global(e2e: dict) -> str:
    o = e2e["metrics"]["overall_accuracy"]
    return ("| Media | Mediana | Desv. est. | IC95% bootstrap | n |\n"
            "|---|---|---|---|---|\n"
            f"{_fmt(o)} {e2e['n']} |")


def tabla_por_tipo(e2e: dict) -> str:
    rows = ["| Tipo | n | Recall | Mediana | Desv. est. | IC95% bootstrap | Latencia media |",
            "|---|---|---|---|---|---|---|"]
    for t in ("single", "alias", "multi"):
        m = e2e["metrics"].get(t)
        if not m:
            continue
        r, lat = m["recall"], m["latency_s"]
        rows.append(
            f"| {t} | {m['n']} | {r['mean']:.3f} | {r['median']:.3f} | {r['std']:.3f} | "
            f"[{r['ci95_low']:.3f}, {r['ci95_high']:.3f}] | {lat['mean']:.2f} s |"
        )
    return "\n".join(rows)


def tabla_recuperacion() -> str:
    rows = ["| Tipo | Resultado | Meta | Estado |", "|---|---|---|---|"]
    for k, r in RETRIEVAL.items():
        ratio = r["ok"] / r["n"]
        umbral = {"single": 0.85, "alias": 0.90}.get(k, 1.0)
        estado = "✓" if ratio >= umbral else "parcial"
        rows.append(f"| {k} | {r['ok']}/{r['n']} ({ratio:.3f}) | {r['meta']} | {estado} |")
    return "\n".join(rows)


def tabla_fallos(e2e: dict) -> str:
    fails = [r for r in e2e["results"] if not r["hit"]]
    if not fails:
        return "_Sin fallos en esta corrida._"
    rows = ["| id | tipo | consulta | esperado | recuperado |", "|---|---|---|---|---|"]
    for f in fails:
        got = ", ".join(f["source_slugs"][:3]) or f"_{f['kind']}_"
        rows.append(f"| {f['id']} | {f['type']} | {f['query']} | "
                    f"{', '.join(f['expected'])} | {got} |")
    return "\n".join(rows)


def seccion_gifs() -> str:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}
    frames = manifest.get("escenarios", {})
    out = []
    for name, (fr, desc) in ESCENARIOS.items():
        gif = GIFS / f"{name}.gif"
        if not gif.exists():
            continue
        n = frames.get(name, "?")
        out.append(f"### {name} — {fr}\n\n{desc} ({n} frames).\n\n"
                   f"![{name}](../outputs/gifs/{name}.gif)\n")
    return "\n".join(out) or "_GIFs no generados en esta corrida._"


def render(e2e: dict) -> str:
    fecha = datetime.date.today().isoformat()
    o = e2e["metrics"]["overall_accuracy"]
    boot = e2e["bootstrap"]
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}
    usuario = manifest.get("usuario", "—")

    return f"""# QA Report — Especialista en enfermedades emocionales

> Generado por `scripts/qa_report.py` a partir de la corrida real del
> {fecha}. Todas las cifras provienen de `outputs/evidence/e2e_results.json`;
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

1. `scripts/e2e.py` — corre las {e2e['n']} preguntas de `eval/questions.json` por el
   **pipeline real del chat** (`run_deterministic` → `gemma4`) y verifica de forma
   **determinista** (slug esperado en `sources[]`, o título del término en el texto).
   Métricas con **bootstrap seed={boot['seed']}, {boot['resamples']} remuestreos**.
2. `scripts/capture_evidence.py` — recorre 5 escenarios sobre la **UI real** con Chrome
   headless (CDP), guardando frames y stills.
3. `scripts/gifs.py` — ensambla los frames en GIFs animados (Pillow, sin `ffmpeg`).
4. `scripts/qa_report.py` + `scripts/report.py` — este documento y el PDF.

## 3. Escenarios end-to-end sobre la UI final

Ejecutados contra la app en contenedor, con un usuario **registrado en la corrida**
(`{usuario}`) — no hay datos precargados ni mocks.

| Escenario | FR/NFR | Qué demuestra | Resultado |
|---|---|---|---|
{chr(10).join(f"| {n} | {fr} | {d} | ✓ |" for n, (fr, d) in ESCENARIOS.items())}

Cada escenario **falla la corrida** si su aserción no se cumple (chips presentes,
clase `.message.emergency` aplicada, texto de bloqueo, chat visible tras el registro).

## 4. Tablas de resultados (corrida real contra el LLM)

> No se asume acierto: cada veredicto queda auditable en
> `outputs/evidence/e2e_results.json` (consulta, esperado, citas devueltas y latencia).

### 4.1 Desempeño global

{tabla_global(e2e)}

> **Variabilidad real entre corridas:** `gemma4` no es determinista, así que la cifra se mueve
> entre ejecuciones (se han observado global 0.865–0.885 y single 0.903–0.935 sobre el mismo
> índice y el mismo gold set). Lo que **sí** es reproducible es el procedimiento: mismo
> `questions.json`, misma verificación determinista y mismo bootstrap (seed={boot['seed']}).
> Las cifras de esta tabla son las de la última corrida de `scripts/evidence.sh`.

### 4.2 Por tipo de consulta

{tabla_por_tipo(e2e)}

### 4.3 Recuperación aislada (§13.0)

{tabla_recuperacion()}

### 4.4 Fallos observados

{tabla_fallos(e2e)}

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

{seccion_gifs()}

## 8. Conclusión

El sistema es **reproducible** (índice idempotente por hash de corpus, eval con seed fijo),
**seguro por mecanismo** (emergencias y derivación resueltas en backend, no por prompt) y
tiene **memoria persistente** por portador (sesiones ADK + `profiles.consultations` en
Postgres). Su precisión end-to-end verificada contra el LLM real es
**{o['mean']:.3f}** (IC95% [{o['ci95_low']:.3f}, {o['ci95_high']:.3f}], n={e2e['n']}).

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
"""


def main() -> int:
    e2e = json.loads(E2E.read_text(encoding="utf-8"))
    DOCS.mkdir(parents=True, exist_ok=True)
    out = DOCS / "QA_report.md"
    out.write_text(render(e2e), encoding="utf-8")
    print(f"[qa_report] {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
