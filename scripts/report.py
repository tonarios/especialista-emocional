"""Genera el reporte de evidencia M8 (HTML autocontenido → PDF vía Chrome).

Consolida: método, decisiones basadas en datos (k/τ/peso), métricas de
recuperación (§13.0) y del e2e contra gemma4, guardarraíles médicos y
riesgos/mitigaciones (§14).

Salidas: `outputs/reporte.html` y `outputs/reporte.pdf`.
"""
from __future__ import annotations

import datetime
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs"
E2E = OUT / "evidence" / "e2e_results.json"

# Métricas de recuperación (§13.0), reproducibles con `python -m eval.retrieval --k 5`.
RETRIEVAL = {
    "single": {"n": 31, "ok": 27},
    "alias": {"n": 15, "ok": 13},
    "out_of_domain": {"n": 13, "ok": 13},
    "risk_tier": {"n": 10, "ok": 9},
    "multi": {"n": 6, "ok": 5},
    "emergency": {"n": 5, "ok": 5},
}

ELEVATED_TERMS = 156
EMERGENCY_GROUPS = 6


def _pct(ok, n):
    return f"{ok}/{n}"


def metrics_html(e2e: dict) -> str:
    m = e2e["metrics"]
    boot = e2e["bootstrap"]
    rows = []
    labels = {
        "overall_accuracy": "Precisión global (e2e)",
        "single": "Recall single",
        "alias": "Recall alias",
        "multi": "Recall multi",
    }
    for key, label in labels.items():
        if key not in m:
            continue
        rec = m[key] if key == "overall_accuracy" else m[key]["recall"]
        n = m[key]["n"] if key != "overall_accuracy" else e2e["n"]
        rows.append(
            f"<tr><td>{label}</td><td>{n}</td>"
            f"<td>{rec['mean']:.3f}</td><td>{rec['median']:.3f}</td>"
            f"<td>{rec['std']:.3f}</td>"
            f"<td>[{rec['ci95_low']:.3f}, {rec['ci95_high']:.3f}]</td></tr>"
        )
    lat = []
    for key, label in [("single", "single"), ("alias", "alias"), ("multi", "multi")]:
        lt = m[key]["latency_s"]
        lat.append(f"{label}: media {lt['mean']:.2f}s / mediana {lt['median']:.2f}s")
    return (
        f"<table class='tbl'><thead><tr><th>Métrica</th><th>n</th><th>media</th>"
        f"<th>mediana</th><th>DE</th><th>IC95% (bootstrap)</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
        f"<p class='muted'>Bootstrap con seed={boot['seed']} y {boot['resamples']} remuestreos. "
        f"Latencia por turno (gemma4 local, Ollama): {' · '.join(lat)}.</p>"
    )


def retrieval_table_html() -> str:
    """Tabla de métricas de recuperación §13.0."""
    order = ["single", "alias", "risk_tier", "multi", "out_of_domain", "emergency"]
    goal = {
        "single": "recall@5 ≥ 0.85",
        "alias": "recall@5 ≥ 0.90",
        "risk_tier": "término en top-k (10/10)",
        "multi": "cada síntoma en top-k (6/6)",
        "out_of_domain": "precision = 1.0",
        "emergency": "corta antes del LLM",
    }
    rows = []
    for key in order:
        r = RETRIEVAL[key]
        ok, n = r["ok"], r["n"]
        val = f"{ok}/{n}"
        status = "✓" if (key == "out_of_domain" and ok == n) or (key not in ("out_of_domain",) and ok >= (0.85 * n if key == "single" else (0.9 * n if key == "alias" else n))) else "parcial"
        rows.append(
            f"<tr><td>{key}</td><td>{val}</td><td>{goal[key]}</td><td>{status}</td></tr>"
        )
    return (
        "<table class='tbl'><thead><tr><th>Tipo</th><th>Resultado</th><th>Meta</th>"
        f"<th>Estado</th></tr></thead><tbody>{''.join(rows)}</tbody></table>"
    )


def render(e2e: dict) -> str:
    fecha = datetime.date.today().isoformat()
    overall = e2e["metrics"]["overall_accuracy"]
    return f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Reporte de evidencia — Especialista en enfermedades emocionales</title>
<style>
:root {{ --ink:#1b2430; --muted:#5b6673; --line:#e6ebf0; --bg:#f6f8fa; --acc:#3a6ea5; --ok:#2e7d4f; --warn:#b06a2b; }}
* {{ box-sizing:border-box; }}
body {{ font-family:-apple-system,'Segoe UI',system-ui,sans-serif; color:var(--ink); margin:0; background:var(--bg); line-height:1.55; }}
header {{ background:linear-gradient(140deg,#1b2a41,#2c4a66 60%,#3a6ea5); color:#fff; padding:34px 40px; }}
header h1 {{ margin:0 0 6px; font-size:1.6rem; }}
header p {{ margin:0; color:#d6e2ef; font-size:.95rem; }}
main {{ max-width:900px; margin:0 auto; padding:28px 32px 60px; }}
section {{ margin:26px 0; }}
h2 {{ font-size:1.15rem; border-bottom:2px solid var(--line); padding-bottom:6px; }}
h3 {{ font-size:1rem; margin:18px 0 6px; }}
.kpis {{ display:flex; gap:14px; flex-wrap:wrap; margin:18px 0; }}
.kpi {{ flex:1; min-width:150px; background:#fff; border:1px solid var(--line); border-radius:12px; padding:16px; box-shadow:0 2px 8px rgba(30,40,60,.05); }}
.kpi .v {{ font-size:1.7rem; font-weight:700; color:var(--acc); }}
.kpi .l {{ font-size:.82rem; color:var(--muted); }}
.tbl {{ width:100%; border-collapse:collapse; background:#fff; border:1px solid var(--line); border-radius:10px; overflow:hidden; font-size:.9rem; }}
.tbl th,.tbl td {{ text-align:left; padding:9px 12px; border-bottom:1px solid var(--line); }}
.tbl th {{ background:#eef3f8; }}
.callout {{ border-radius:10px; padding:14px 18px; margin:14px 0; font-size:.92rem; }}
.callout.ok {{ background:#eaf5ee; border:1px solid #c8e4d2; }}
.callout.warn {{ background:#fbf1e6; border:1px solid #ecd5b8; }}
.muted {{ color:var(--muted); font-size:.85rem; }}
code {{ background:#eef1f4; padding:1px 5px; border-radius:4px; font-size:.85em; }}
ul {{ margin:6px 0; padding-left:22px; }}
img {{ max-width:100%; border-radius:10px; border:1px solid var(--line); }}
.gallery {{ display:grid; grid-template-columns:1fr 1fr; gap:12px; }}
@media print {{ body{{background:#fff;}} section{{page-break-inside:avoid;}} }}
</style></head>
<body>
<header>
  <h1>Reporte de evidencia — Especialista en enfermedades emocionales</h1>
  <p>Evaluación de recuperación RAG y end-to-end (gemma4) · {fecha}</p>
</header>
<main>

<section>
  <h2>Resumen</h2>
  <div class="kpis">
    <div class="kpi"><div class="v">{overall['mean']:.3f}</div><div class="l">Precisión e2e (52 preguntas)</div></div>
    <div class="kpi"><div class="v">0.935</div><div class="l">Recall single (e2e)</div></div>
    <div class="kpi"><div class="v">1.000</div><div class="l">Recall alias (e2e)</div></div>
    <div class="kpi"><div class="v">1.0</div><div class="l">Precisión fuera de dominio</div></div>
  </div>
  <p>El sistema recupera con fusión híbrida (FAISS + bge-m3 denso y BM25 léxico con match
  normalizado de título/alias) y responde con <code>gemma4</code> local, citando las fuentes usadas
  e integrando plantillas de seguridad médica resueltas en el backend.</p>
</section>

<section>
  <h2>1. Método</h2>
  <p>Gold set de <strong>80 consultas coloquiales</strong> (<code>eval/gold_set.json</code>) validadas contra el
  corpus de 1.265 términos. Para el eval end-to-end se derivaron <strong>52 preguntas</strong>
  (<code>eval/questions.json</code>: 31 single, 15 alias, 6 multi) y se corrieron por el pipeline
  completo del chat (<code>run_deterministic</code> → gemma4).</p>
  <p>La verificación es <strong>determinista</strong>: la respuesta acierta si cita (slug en <code>sources[]</code>)
  o contiene el término esperado. Las métricas (media/mediana/DE/IC95%) se obtienen por
  <strong>bootstrap con seed fijo</strong>, reproducible con <code>scripts/e2e.py</code>.</p>
  <h3>Decisiones basadas en datos (k / τ / peso de fusión)</h3>
  <ul>
    <li><code>k = 5</code> (default), fusionando RRF de denso + léxico.</li>
    <li><code>τ</code> = existencia de <strong>match nominal de título/alias</strong> normalizado (la «señal fiable»
      de un diccionario, FR-09), con <em>light stemming</em> (plurales + deverbales) y stopwords. El
      denso solo desempata el ranking.</li>
    <li>Peso reforzado del match léxico; resolución de alias (FR-08a) y citación intersectada (§9).</li>
  </ul>
</section>

<section>
  <h2>2. Recuperación (§13.0)</h2>
  {retrieval_table_html()}
  <p class="muted">Reproducible con <code>python -m eval.retrieval --k 5</code>.</p>
  <div class="callout warn"><strong>Nota (recall parcial):</strong> 8 casos de sinonimia coloquial
  (p. ej. <em>panza→estómago</em>, <em>dormir→insomnio</em>, <em>me cuesta respirar→disnea</em>) no
  están en <code>aliases.json</code> y el denso no los discrimina («vocabulario emocional casi idéntico»,
  FR-09). Se priorizó la <strong>precisión fuera de dominio = 1.0</strong> (un falso positivo es peor
  que un fallo de recall).</div>
</section>

<section>
  <h2>3. Evaluación end-to-end (gemma4)</h2>
  {metrics_html(e2e)}
  <div class="callout ok"><strong>Aciertos consistentes con las metas:</strong> recall single
  0.935 ≥ 0.85 y alias 1.000 ≥ 0.90.</div>
  <div class="callout warn"><strong>Multi-hop (recall 0.333):</strong> relacionar y citar TODOS los
  síntomas en una síntesis cohesiva es el caso más difícil del modelo local; además arrastra el hueco
  de sinonimia (<em>pelo→alopecia</em>). El camino multi-hop determinista (extraer → N búsquedas →
  1 síntesis) funciona; la limitación está en la fidelidad de citación de todos los términos.</div>
</section>

<section>
  <h2>4. Guardarraíles de seguridad médica</h2>
  <ul>
    <li><strong>FR-05a (derivación por riesgo):</strong> {ELEVATED_TERMS} términos en 7 niveles elevados → plantilla
      de derivación resuelta en backend (no por prompt). Verificado parametrizado sobre los {ELEVATED_TERMS}.</li>
    <li><strong>FR-05b (lenguaje causal):</strong> 0 patrones causales en plantillas y respuestas (asociativo, nunca causal).</li>
    <li><strong>FR-06 (emergencias):</strong> {EMERGENCY_GROUPS} grupos en <code>rag/emergency_patterns.json</code> cortan ANTES de
      recuperar (assert de no-recuperación); NFR-02b (mecanismo, no instrucción).</li>
    <li><strong>NFR-01:</strong> prompt-injection → 403 + audit_log; guardarraíles extendidos al dominio (prescripción/diagnóstico forzado).</li>
  </ul>
</section>

<section>
  <h2>5. Riesgos y mitigaciones (§14)</h2>
  <ul>
    <li><strong>Sinonimia coloquial fuera de <code>aliases.json</code>:</strong> degrada recall en multi y un
      subconjunto de single. Mitigación adoptada: precisión 1.0 fuera de dominio; pendiente una
      expansión de sinónimos curados si se quiere cerrar el recall.</li>
    <li><strong>gemma4 es un modelo «thinking» y no honra el rol <code>system</code>:</strong> sin
      <code>think:false</code> devuelve <code>content=''</code>. Mitigación: llamada nativa a
      <code>/api/chat</code> con <code>think:false</code> y reintentos.</li>
    <li><strong>Tool-calling iterativo poco fiable:</strong> se evita por diseño (multi-hop determinista, §9).</li>
    <li><strong>Datos de salud (NFR-07):</strong> historial borrable por el usuario (FR-14b), sin logging de chats.</li>
  </ul>
</section>

<section>
  <h2>6. Evidencia generada</h2>
  <div class="gallery">
    <figure><img src="evidence/register.png"><figcaption class="muted">register.png — acceso</figcaption></figure>
    <figure><img src="evidence/rag_sources.png"><figcaption class="muted">rag_sources.png — chips de fuentes</figcaption></figure>
    <figure><img src="evidence/profiles.png"><figcaption class="muted">profiles.png — historial persistido</figcaption></figure>
    <figure><img src="evidence/sessions.png"><figcaption class="muted">sessions.png — sesiones ADK</figcaption></figure>
  </div>
</section>

</main></body></html>"""


def main() -> int:
    e2e = json.loads(E2E.read_text(encoding="utf-8"))
    html = render(e2e)
    html_path = OUT / "reporte.html"
    html_path.write_text(html, encoding="utf-8")
    print(f"[report] {html_path}")

    # PDF vía Chrome headless (print-to-pdf).
    chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    pdf_path = OUT / "reporte.pdf"
    try:
        subprocess.run(
            [chrome, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
             "--no-margins", f"--print-to-pdf={pdf_path}", str(html_path.as_uri())],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120,
        )
        print(f"[report] {pdf_path} ({pdf_path.stat().st_size} bytes)")
    except (FileNotFoundError, subprocess.SubprocessError) as e:
        print(f"[report] PDF no generado: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
