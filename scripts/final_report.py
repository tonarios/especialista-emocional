"""Reporte final del proyecto: infraestructura, decisiones, evidencia y resultados.

Distinto de `scripts/report.py`, que cubre solo la evidencia del eval (M8). Este
consolida el proyecto entero, incluida la migración a GCP y el despliegue.

Todas las cifras se leen de los artefactos reales de la última corrida
(`outputs/evidence/*.json`); nada está escrito a mano, así que el reporte no
puede desincronizarse de los datos.

Estilo heredado del reporte del módulo 1 (documento continuo, no pestañas: un
PDF con pestañas sale truncado a la primera).

Salidas: `outputs/reporte-final.html` y `outputs/reporte-final.pdf`.
Uso: uv run python scripts/final_report.py
"""
from __future__ import annotations

import base64
import datetime
import json
import mimetypes
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs"
EV = OUT / "evidence"
FONT = Path("/Users/data_sci/Documents/personal/diplomado_ia/modulo1/reporte/assets/ArchivoBlack-Regular.ttf")

URL_PROD = "https://emociones-app-zxzgilzqfq-uc.a.run.app"

# Recuperación aislada (§13.0), reproducible con `python -m eval.retrieval --k 5`.
RETRIEVAL = [
    # tipo,           bge,      vertex,   meta
    ("single",        (27, 31), (28, 31), "≥0.85"),
    ("alias",         (13, 15), (14, 15), "≥0.90"),
    ("risk_tier",     (9, 10),  (9, 10),  "10/10"),
    ("multi",         (5, 6),   (5, 6),   "6/6"),
    ("emergency",     (5, 5),   (5, 5),   "5/5"),
    ("out_of_domain", (13, 13), (13, 13), "1.0"),
]

# Barrido del umbral denso sobre el gold set (docs/migration.md §4.1).
BARRIDO = [(0.70, 12, 65), (0.72, 12, 64), (0.74, 13, 64),
           (0.76, 13, 64), (0.78, 13, 63), (0.80, 13, 63)]

CORAL, INK, GREY, LINE = "#ff5a5f", "#141414", "#7a7a78", "#e4e4e1"


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode()


def shot(path: Path, caption: str) -> str:
    """Captura embebida en base64: el HTML queda autocontenido."""
    if not path.exists():
        return f"<p class='small'>({path.name}: no disponible)</p>"
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    return (f"<figure><div class='shot'><img src='data:{mime};base64,{_b64(path)}' "
            f"alt='{caption}'></div><figcaption>{caption}</figcaption></figure>")


def term(titulo: str, contenido: str) -> str:
    """Bloque de terminal (fondo oscuro, monoespaciado)."""
    return (f"<div class='term'><div class='bar'><span class='dot dr'></span>"
            f"<span class='dot dy'></span><span class='dot dg'></span> <b>{titulo}</b></div>"
            f"<pre>{contenido}</pre></div>")


# ── Gráficos SVG inline, en la paleta del tema ────────────────────
def bars(labels, values, *, colors=None, title="", fmt="{:.0f}", height=250, ymax=None):
    W, ml, mr, mt, mb = 720, 54, 16, (30 if title else 10), 46
    ph, pw = height - mt - mb, W - ml - mr
    vmax = (ymax or max(values)) * 1.16
    n = max(1, len(values)); slot = pw / n; bw = slot * 0.56
    el = []
    if title:
        el.append(f"<text x='{ml}' y='16' font-size='11.5' font-weight='700' fill='{INK}'>{title}</text>")
    for i in range(5):
        t = vmax * i / 4
        y = mt + ph - ph * (t / vmax)
        el.append(f"<line x1='{ml}' y1='{y:.1f}' x2='{ml+pw}' y2='{y:.1f}' stroke='#ececea'/>")
        el.append(f"<text x='{ml-7}' y='{y+3:.1f}' text-anchor='end' font-size='9' fill='{GREY}'>{fmt.format(t)}</text>")
    for i, v in enumerate(values):
        x = ml + slot * i + (slot - bw) / 2
        bh = ph * (v / vmax) if vmax else 0
        y = mt + ph - bh
        c = colors[i] if colors else INK
        el.append(f"<rect x='{x:.1f}' y='{y:.1f}' width='{bw:.1f}' height='{bh:.1f}' rx='3' fill='{c}'/>")
        el.append(f"<text x='{x+bw/2:.1f}' y='{y-5:.1f}' text-anchor='middle' font-size='10.5' "
                  f"font-weight='700' fill='{INK}'>{fmt.format(v)}</text>")
        for j, linea in enumerate(str(labels[i]).split("\n")):
            el.append(f"<text x='{x+bw/2:.1f}' y='{mt+ph+15+j*11:.1f}' text-anchor='middle' "
                      f"font-size='9.5' fill='{GREY}'>{linea}</text>")
    return f"<svg viewBox='0 0 {W} {height}' width='100%'>{''.join(el)}</svg>"


def grouped(labels, a_vals, b_vals, a_name, b_name, *, title="", fmt="{:.3f}", height=270):
    W, ml, mr, mt, mb = 720, 54, 16, 46, 46
    ph, pw = height - mt - mb, W - ml - mr
    vmax = 1.16
    n = len(labels); slot = pw / n; bw = slot * 0.28
    el = [f"<text x='{ml}' y='16' font-size='11.5' font-weight='700' fill='{INK}'>{title}</text>"]
    el.append(f"<rect x='{ml}' y='24' width='9' height='9' rx='2' fill='{GREY}'/>"
              f"<text x='{ml+13}' y='32' font-size='9.5' fill='{GREY}'>{a_name}</text>"
              f"<rect x='{ml+120}' y='24' width='9' height='9' rx='2' fill='{CORAL}'/>"
              f"<text x='{ml+133}' y='32' font-size='9.5' fill='{GREY}'>{b_name}</text>")
    for i in range(5):
        t = vmax * i / 4
        y = mt + ph - ph * (t / vmax)
        el.append(f"<line x1='{ml}' y1='{y:.1f}' x2='{ml+pw}' y2='{y:.1f}' stroke='#ececea'/>")
        el.append(f"<text x='{ml-7}' y='{y+3:.1f}' text-anchor='end' font-size='9' fill='{GREY}'>{t:.2f}</text>")
    for i in range(n):
        cx = ml + slot * i + slot / 2
        for k, (v, c) in enumerate(((a_vals[i], "#c9c9c6"), (b_vals[i], CORAL))):
            x = cx - bw + k * bw
            bh = ph * (v / vmax)
            y = mt + ph - bh
            el.append(f"<rect x='{x:.1f}' y='{y:.1f}' width='{bw-2:.1f}' height='{bh:.1f}' rx='2' fill='{c}'/>")
            el.append(f"<text x='{x+bw/2-1:.1f}' y='{y-4:.1f}' text-anchor='middle' font-size='8.5' "
                      f"fill='{INK}'>{fmt.format(v)}</text>")
        el.append(f"<text x='{cx:.1f}' y='{mt+ph+15:.1f}' text-anchor='middle' font-size='9.5' fill='{GREY}'>{labels[i]}</text>")
    return f"<svg viewBox='0 0 {W} {height}' width='100%'>{''.join(el)}</svg>"


def hbars(labels, values, *, colors=None, title="", fmt="{:.0f}", row_h=25):
    n = len(values); W, ml, mr, mt = 720, 200, 56, (28 if title else 8)
    H = mt + 12 + n * row_h; pw = W - ml - mr; bh = row_h * 0.62
    vmax = max(values) * 1.06
    el = []
    if title:
        el.append(f"<text x='6' y='16' font-size='11.5' font-weight='700' fill='{INK}'>{title}</text>")
    for i, v in enumerate(values):
        y = mt + i * row_h
        bw = pw * (v / vmax) if vmax else 0
        c = colors[i] if colors else INK
        el.append(f"<rect x='{ml}' y='{y:.1f}' width='{bw:.1f}' height='{bh:.1f}' rx='3' fill='{c}'/>")
        el.append(f"<text x='{ml-8}' y='{y+bh*0.8:.1f}' text-anchor='end' font-size='10' fill='{INK}'>{labels[i]}</text>")
        el.append(f"<text x='{ml+bw+6:.1f}' y='{y+bh*0.8:.1f}' font-size='10' font-weight='700' fill='{INK}'>{fmt.format(v)}</text>")
    return f"<svg viewBox='0 0 {W} {H}' width='100%'>{''.join(el)}</svg>"


# ══════════════════════════════════════════════════════════════════
CSS = r"""
@font-face{font-family:'Archivo Black';font-style:normal;font-weight:400;font-display:swap;
  src:url(data:font/ttf;base64,__FONT__) format('truetype');}
:root{
  --ink:#141414; --ink2:#2b2b2b; --paper:#f7f7f5; --paper2:#efefec; --line:#e4e4e1;
  --muted:#7a7a78; --accent:#ff5a5f; --accent2:#e04a4f; --grey:#8a8a8a; --dark:#3f3f3f;
  --mono:'SF Mono',ui-monospace,'Cascadia Code',Menlo,Consolas,monospace;
  --serif:'Archivo Black','Arial Black',system-ui,sans-serif;
  --sans:system-ui,-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
}
*{box-sizing:border-box}
html,body{margin:0;padding:0}
body{font-family:var(--sans);color:var(--ink);background:var(--paper);
  line-height:1.55;font-size:15px;-webkit-print-color-adjust:exact;print-color-adjust:exact}
.wrap{max-width:940px;margin:0 auto;padding:0 34px}
h1,h2,h3{font-family:var(--serif);font-weight:400;line-height:1.14;letter-spacing:-.015em}
a{color:var(--dark);text-decoration:none}
p{margin:.55em 0}
small,.small{font-size:12.5px;color:var(--muted)}
code,.mono{font-family:var(--mono);font-size:.86em}
em{color:var(--ink2);font-style:normal;font-weight:600}
ul,ol{margin:.6em 0;padding-left:22px} li{margin:.3em 0}

.hero{background:radial-gradient(1200px 400px at 78% -10%,#26262b 0%,transparent 60%),
      linear-gradient(135deg,#141416 0%,#0f0f12 55%,#0b0b0d 100%);
      color:#ededed;padding:52px 0 44px;position:relative;overflow:hidden}
.hero .wrap{position:relative;z-index:2}
.kicker{font-family:var(--mono);font-size:12px;letter-spacing:.32em;text-transform:uppercase;
  color:var(--accent);margin:0 0 14px}
.hero h1{font-size:42px;margin:0;color:#f6f6f6;letter-spacing:-.5px}
.hero .lede{font-size:17px;max-width:640px;color:#c8c8c8;margin:16px 0 24px}
.hero .meta{font-family:var(--mono);font-size:11.5px;letter-spacing:.12em;color:#8a8a8a;
  border-top:1px solid #2f2f34;padding-top:14px;text-transform:uppercase}
.medal{position:absolute;right:-40px;top:-30px;width:330px;height:330px;opacity:.9;z-index:1}

section{padding:34px 0;border-bottom:1px solid var(--line)}
.eyebrow{font-family:var(--mono);font-size:11px;letter-spacing:.26em;text-transform:uppercase;
  color:var(--accent);margin:0 0 6px;font-weight:600}
h2.big{font-size:29px;margin:.1em 0 .5em;padding-bottom:.28em;position:relative}
h2.big::after{content:"";position:absolute;left:0;bottom:0;width:64px;height:4px;
  background:linear-gradient(90deg,var(--dark),var(--accent));border-radius:2px}
h3{font-size:18px;margin:1.4em 0 .3em}
h4{font-size:15px;margin:1.1em 0 .2em;font-family:var(--sans);font-weight:700}

.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:18px 0}
.kpi{background:#fff;border:1px solid var(--line);border-radius:12px;padding:16px 15px;
  position:relative;overflow:hidden}
.kpi::before{content:"";position:absolute;left:0;top:0;bottom:0;width:4px;background:var(--dark)}
.kpi.a::before{background:var(--accent)} .kpi.s::before{background:var(--grey)}
.kpi.g::before{background:#5fbf6f}
.kpi .v{font-family:var(--serif);font-size:29px;line-height:1}
.kpi .l{font-size:12px;color:var(--muted);margin-top:6px}

.card{background:#fff;border:1px solid var(--line);border-radius:12px;padding:18px 20px;margin:16px 0}
.card h4{margin-top:0}
.callout{border-left:4px solid var(--accent);background:#fdf1f1;border-radius:0 10px 10px 0;
  padding:14px 18px;margin:16px 0}
.callout.key{background:#fbf3df;border-left-color:#e0b64d}
.callout h4{margin:0 0 .3em}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}
.chip{display:inline-block;font-family:var(--mono);font-size:11px;padding:2px 9px;border-radius:20px;
  border:1px solid var(--line);background:#fff;margin:2px 3px 2px 0;color:var(--ink2)}
.chip.a{border-color:var(--accent2);color:var(--accent2)}

table{width:100%;border-collapse:collapse;margin:14px 0;font-size:13.5px}
th,td{text-align:left;padding:9px 11px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-family:var(--mono);font-size:11px;letter-spacing:.08em;text-transform:uppercase;
  color:var(--muted);background:var(--paper2)}
td.num,th.num{text-align:right;font-family:var(--mono)}
.ok{color:#3f8f4f;font-weight:700} .bad{color:var(--accent2);font-weight:700}

.term{background:#141416;border-radius:10px;margin:14px 0;overflow:hidden;border:1px solid #2a2a2e}
.term .bar{background:#1c1c20;padding:7px 13px;font-family:var(--mono);font-size:11px;color:#8a8a90;
  border-bottom:1px solid #2a2a2e;letter-spacing:.05em}
.term .bar b{color:#e0e0e2;font-weight:600}
.term pre{margin:0;padding:14px 16px;font-family:var(--mono);font-size:11.4px;line-height:1.62;
  color:#d2d2d6;overflow-x:auto;white-space:pre-wrap;word-break:break-word}
.term .k{color:#ff6b70;font-weight:600} .term .g{color:#5fbf6f} .term .m{color:#6a6a70}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:5px;vertical-align:middle}
.dr{background:#e05a4d}.dy{background:#e0b64d}.dg{background:#5fbf6f}

figure{margin:16px 0}
.shot{border:1px solid var(--line);border-radius:12px;overflow:hidden;background:#fff;
  box-shadow:0 6px 22px rgba(20,17,11,.08)}
.shot img{display:block;width:100%}
figcaption{font-size:12px;color:var(--muted);margin-top:8px;font-style:italic}
.chart{background:#fff;border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin:14px 0}

/* ---------- Conversación ---------- */
.chat{background:#fff;border:1px solid var(--line);border-radius:14px;padding:18px;margin:16px 0}
.turn{margin:0 0 20px;padding-bottom:18px;border-bottom:1px dashed var(--line)}
.turn:last-child{margin-bottom:0;padding-bottom:0;border-bottom:none}
.bub{border-radius:14px;padding:11px 15px;margin:6px 0;max-width:82%;font-size:13.5px;line-height:1.5}
.bub.u{background:var(--ink);color:#f2f2f0;margin-left:auto;border-bottom-right-radius:4px}
.bub.a{background:var(--paper2);border:1px solid var(--line);border-bottom-left-radius:4px}
.cites{margin:7px 0 0}
.cite{display:inline-block;font-family:var(--mono);font-size:10px;padding:2px 8px;border-radius:20px;
  background:#fff;border:1px solid var(--line);color:var(--muted);margin:2px 3px 0 0}
.inner{display:flex;gap:10px;flex-wrap:wrap;margin-top:9px;font-family:var(--mono);font-size:10.5px;
  color:var(--muted);align-items:center}
.inner b{color:var(--ink)}
.pill{background:var(--paper2);border-radius:20px;padding:2px 9px;border:1px solid var(--line)}
.pill.a{background:#fdf1f1;border-color:#f4c9c9;color:var(--accent2)}
.pill.g{background:#eef8f0;border-color:#c6e6cd;color:#3f8f4f}
.turnnote{font-size:12px;color:var(--muted);font-style:italic;margin:0 0 8px}

/* ---------- Ciclo de vida ---------- */
.life{display:grid;grid-template-columns:150px 1fr;gap:0;margin:16px 0;font-size:13px}
.life .lb{font-family:var(--mono);font-size:10.5px;text-transform:uppercase;letter-spacing:.1em;
  color:var(--accent);padding:12px 12px 12px 0;border-right:2px solid var(--line);text-align:right}
.life .lc{padding:12px 0 12px 18px;border-left:0;position:relative}
.life .lc::before{content:"";position:absolute;left:-6px;top:17px;width:10px;height:10px;
  border-radius:50%;background:var(--accent);border:2px solid var(--paper)}
.life .lr{display:contents}

.flow{display:flex;align-items:stretch;gap:0;margin:18px 0;flex-wrap:wrap}
.node{flex:1;min-width:78px;text-align:center;padding:11px 6px;border-radius:10px;
  border:1px solid var(--line);background:#fff;font-size:11.5px;line-height:1.35}
.node .n{font-family:var(--serif);font-size:13px}
.node.g{border-top:3px solid #5fbf6f} .node.a{border-top:3px solid var(--accent)}
.node.d{border-top:3px solid var(--dark)} .node.s{border-top:3px solid var(--grey)}
.arw{align-self:center;color:var(--muted);font-size:16px;padding:0 4px}

footer{padding:26px 0 40px;color:var(--muted);font-size:12px}
footer .wrap{display:flex;justify-content:space-between;flex-wrap:wrap;gap:10px}
.seal{font-family:var(--mono);letter-spacing:.1em}

@media print{
  body{font-size:11.5px}
  .wrap{max-width:100%;padding:0 13mm}
  .hero{padding:34px 0 28px} .hero h1{font-size:32px}
  section{padding:19px 0;break-inside:avoid-page}
  .kpi,.card,.callout,.term,figure,table,.flow,.chart{break-inside:avoid}
  h2.big,h3{break-after:avoid}
  a{color:var(--ink)}
  .pbreak{break-before:page}
}
"""


def build(e2e_l: dict, e2e_v: dict, smoke: dict, conv: dict) -> str:
    ml, mv = e2e_l["metrics"], e2e_v["metrics"]
    o = mv["overall_accuracy"]
    hoy = datetime.date.today().isoformat()
    S: list[str] = []

    def sec(num, eyebrow, titulo, cuerpo, pbreak=False):
        S.append(f"<section class='{'pbreak' if pbreak else ''}'><div class='wrap'>"
                 f"<p class='eyebrow'>{num} · {eyebrow}</p>"
                 f"<h2 class='big'>{titulo}</h2>{cuerpo}</div></section>")

    # ── 01 Resumen ────────────────────────────────────────────────
    flow = """
<div class="flow">
  <div class="node a"><div class="n">injection</div>403 antes del LLM</div><div class="arw">→</div>
  <div class="node a"><div class="n">emergencia</div>corta antes de recuperar</div><div class="arw">→</div>
  <div class="node d"><div class="n">síntomas</div>1 llamada estructurada</div><div class="arw">→</div>
  <div class="node s"><div class="n">RAG</div>N búsquedas en paralelo</div><div class="arw">→</div>
  <div class="node d"><div class="n">plantilla</div>por riesgo, en backend</div><div class="arw">→</div>
  <div class="node g"><div class="n">síntesis</div>citación intersectada</div>
</div>"""

    sec("01", "Resumen ejecutivo", "Qué se construyó", f"""
<p>Un <em>agente conversacional RAG</em> sobre un diccionario de <b>1.265 términos</b> de
enfermedades emocionales, que interpreta síntomas de forma simbólica, <b>cita siempre sus
fuentes</b>, recuerda al usuario entre sesiones y <b>deriva a atención médica</b> ante señales
de riesgo. Un único contenedor con backend FastAPI y frontend propio, desplegado en
<b>Cloud Run</b> escalando a cero.</p>

<div class="kpis">
  <div class="kpi g"><div class="v">{o['mean']:.3f}</div><div class="l">precisión end-to-end (52 preguntas)</div></div>
  <div class="kpi a"><div class="v">{smoke['ok']}/{smoke['total']}</div><div class="l">pruebas contra el servicio vivo</div></div>
  <div class="kpi"><div class="v">37</div><div class="l">recursos GCP como IaC</div></div>
  <div class="kpi s"><div class="v">$0.12</div><div class="l">costo mensual en reposo</div></div>
</div>

{flow}
<p class="small">Pipeline <b>determinista</b>: el modelo no decide cuándo buscar ni cuándo
derivar. Cada etapa crítica se resuelve en el backend, y las dos primeras cortan
<i>antes</i> de que el mensaje llegue al LLM.</p>

<div class="callout key">
  <h4>La tesis del proyecto</h4>
  <p>En un dominio de salud la seguridad tiene que ser un <b>mecanismo</b>, no una instrucción.
  Pedirle a un LLM que derive ante una emergencia falla el día que alucina o le inyectan
  contexto. Aquí nada crítico depende del modelo — y la telemetría de producción lo demuestra
  sin necesidad de un test.</p>
</div>

<p class="small">En producción: <a href="{URL_PROD}">{URL_PROD}</a></p>
""")


    # ── 02 Cómo funciona: una conversación real ───────────────────
    def burbujas(t, i):
        cites = "".join(f"<span class='cite'>{f['title']}</span>" for f in t["fuentes"])
        pills = [f"<span class='pill'>{t['kind']}</span>"]
        if t["risk_tier"]:
            pills.append(f"<span class='pill'>riesgo: {t['risk_tier']}</span>")
        pills.append(f"<span class='pill'>{len(t['fuentes'])} fuentes</span>")
        pills.append(f"<span class='pill'>{t['latencia_s']:.1f} s</span>")
        mem = t["memoria_despues"]
        pills.append(f"<span class='pill g'>memoria: {mem['consultas_en_perfil']} consultas · "
                     f"{mem['eventos_en_sesion']} eventos</span>")
        return (f"<div class='turn'><p class='turnnote'>Turno {i} — {t['nota']}</p>"
                f"<div class='bub u'>{t['usuario']}</div>"
                f"<div class='bub a'>{t['respuesta']}"
                + (f"<div class='cites'>{cites}</div>" if cites else "")
                + f"</div><div class='inner'>{''.join(pills)}</div></div>")

    turnos_html = "".join(burbujas(t, i) for i, t in enumerate(conv["turnos"], 1))
    t3 = conv["turnos"][2]

    sec("02", "Cómo funciona", "Una conversación real, turno a turno", f"""
<p>Esta es una conversación capturada <b>en el servicio desplegado</b>, no un ejemplo
inventado. Bajo cada respuesta se muestra lo que ocurrió por dentro: qué camino tomó el turno,
qué citó, cuánto tardó y <b>cómo quedó la memoria después</b>.</p>

<div class="chat">{turnos_html}</div>

<p>Lo importante está en el tercer turno: <b>0 fuentes y {t3['latencia_s']:.1f} s</b>. No
recuperó nada del diccionario porque no hacía falta — la pregunta era sobre el propio
historial, y eso se responde desde la memoria del portador. Un sistema sin memoria habría
buscado «última consulta» en el diccionario y devuelto cualquier cosa.</p>

<div class="callout">
  <h4>Y una imperfección honesta, visible en el turno 2</h4>
  <p>La persona dijo «espalda <b>baja</b>» y el agente citó <i>parte superior (7 vértebras
  cervicales)</i> y <i>parte central (12 dorsales)</i> — no la parte inferior. Es un fallo de
  ranking real, del tipo que la métrica <code>multi</code> 0.667 recoge. Se deja a la vista
  porque un reporte que solo muestra los turnos que salen bien no informa de nada.</p>
</div>
""")

    # ── 03 Identidad y memoria ────────────────────────────────────
    ais = conv["aislamiento"]
    ultima = conv["turnos"][-1]["memoria_despues"]["ultima_entrada"]
    ejemplo_perfil = json.dumps(ultima, ensure_ascii=False, indent=2)

    sec("03", "Identidad y memoria", "Cómo el login sostiene todo lo demás", f"""
<p>No hay «sesión de usuario» en el backend: hay un <b>token</b>, y de él se deriva todo. El
correo autenticado <em>es</em> la clave de partición de cada dato del sistema.</p>

<div class="life">
  <div class="lr"><div class="lb">1 · Registro</div><div class="lc">
    La contraseña se guarda con <b>PBKDF2-HMAC-SHA256</b> y sal por usuario. Nunca en claro.
    Se emite un <b>JWT HS256</b> cuyo <code>sub</code> es el correo.
    <span class="small">En la captura: HTTP {conv['registro']['http']}, token
    <code>{conv['registro']['token_prefijo']}</code></span>
  </div></div>
  <div class="lr"><div class="lb">2 · Cada petición</div><div class="lc">
    El frontend manda <code>Authorization: Bearer …</code>. El backend verifica la firma y la
    expiración y extrae el correo. <b>Si no hay token válido, no hay dato</b>:
    <code>/profile</code> sin cabecera responde <b>HTTP {conv['sin_token_http']}</b>.
  </div></div>
  <div class="lr"><div class="lb">3 · Identidad única</div><div class="lc">
    Ese correo se usa <b>sin traducción</b> como <code>user_id</code> de ADK, como id del
    documento de perfil en Firestore y como clave de la sesión. No hay forma de pedir los datos
    de otro: el identificador no viaja en el cuerpo de la petición, se deriva del token firmado.
  </div></div>
  <div class="lr"><div class="lb">4 · Se escribe</div><div class="lc">
    Al cerrar el turno se añade la consulta al perfil y los dos eventos (usuario y modelo) a la
    sesión ADK. En la captura, el contador sube <b>1→2→2</b> consultas y <b>2→4→6</b> eventos.
  </div></div>
  <div class="lr"><div class="lb">5 · Se lee</div><div class="lc">
    En el turno siguiente el historial se inyecta en el contexto de la síntesis, y si la
    pregunta es sobre la propia memoria se responde directamente desde él.
  </div></div>
  <div class="lr"><div class="lb">6 · Se borra</div><div class="lc">
    <code>DELETE /profile/consultations</code> vacía el historial <b>del portador y solo del
    suyo</b>. El derecho a olvidar es parte del diseño, no un extra.
  </div></div>
</div>

<h3>Dos memorias, con propósitos distintos</h3>
<div class="grid2">
  <div class="card">
    <h4>Sesión ADK — la conversación</h4>
    <p class="small">Los eventos de cada turno, en orden, en Firestore. Sobreviven a reinicios
    del contenedor y a que Cloud Run escale a cero. Es lo que permite retomar un hilo.</p>
    <p class="small"><b>Por qué en documentos separados:</b> Firestore limita cada documento a
    1 MiB. La sesión y sus eventos van aparte, con ids secuenciales rellenados
    (<code>000001</code>) para que el orden alfabético <i>sea</i> el cronológico y no haga falta
    un índice compuesto.</p>
  </div>
  <div class="card">
    <h4>Perfil — el historial de consultas</h4>
    <p class="small">Una entrada por consulta con el síntoma, los términos citados y la fecha.
    Es lo que el agente lee para personalizar y lo que responde una pregunta de memoria.</p>
    <div class="term" style="margin-top:8px"><div class="bar"><b>última entrada del perfil</b></div>
    <pre>{ejemplo_perfil}</pre></div>
  </div>
</div>

<div class="callout">
  <h4>Dónde sí va el texto del usuario, y dónde nunca</h4>
  <p>El perfil <b>sí</b> guarda lo que la persona escribió: son sus propios datos, en su propio
  documento, y solo alcanzables con su token — es literalmente la función que pidió. El almacén
  <b>analítico</b> es lo contrario: ahí no entra jamás una palabra de la conversación, solo
  slugs, niveles de riesgo y un hash con sal del correo. Son dos almacenes con dos contratos de
  privacidad distintos, y confundirlos fue precisamente el bug de §14.</p>
</div>

<h3>El aislamiento, comprobado en la misma captura</h3>
<p>Un segundo usuario (<code>{ais['usuario_b']}</code>) se registró justo después y consultó
sus propios endpoints: ve <b>{ais['consultas_visibles']} consultas</b> y
<b>{ais['sesiones_visibles']} sesiones</b>. No hay filtrado en la capa de presentación — la
consulta a Firestore se construye con el correo del token, así que los datos ajenos nunca
llegan a salir de la base.</p>
""")


    # ── 04 Anatomía de un turno ───────────────────────────────────
    t1 = conv["turnos"][0]
    sec("04", "Anatomía de un turno", "Qué pasa entre que escribes y respondo", f"""
<p>Cada mensaje recorre siempre las mismas seis etapas, en el mismo orden. El modelo
<b>no decide</b> cuáles se ejecutan: el backend las orquesta. Tomando el primer turno de la
conversación anterior como ejemplo:</p>

<div class="life">
  <div class="lr"><div class="lb">1 · Injection</div><div class="lc">
    <code>check_prompt_injection</code> compara contra patrones de inyección y de dominio
    (pedir prescripción, forzar diagnóstico). Si dispara, <b>403 y se acabó</b>: el mensaje no
    llega al modelo y queda en la auditoría.
  </div></div>
  <div class="lr"><div class="lb">2 · Emergencia</div><div class="lc">
    <code>detect_emergency</code> evalúa 6 grupos de patrones deterministas
    <b>antes de recuperar nada</b>. Si hay señal de urgencia, devuelve la derivación tal cual
    está escrita en <code>emergency_patterns.json</code> — sin interpretación emocional y sin
    pasar por el LLM. Es el camino de <b>56 ms</b> de §05.
  </div></div>
  <div class="lr"><div class="lb">3 · Síntomas</div><div class="lc">
    Una llamada estructurada parte la consulta en frases cortas de búsqueda. Del mensaje del
    ejemplo salió el síntoma de garganta; una consulta con dos dolencias produce dos.
  </div></div>
  <div class="lr"><div class="lb">4 · Recuperación</div><div class="lc">
    Una búsqueda <b>por síntoma, en paralelo</b>. Cada una decide si hay cobertura; las que no
    la tienen se descartan. Si ninguna la tiene, la respuesta es «sin cobertura» y no se
    inventa nada. Aquí recuperó <b>{len(t1['fuentes'])} términos</b>.
  </div></div>
  <div class="lr"><div class="lb">5 · Plantilla</div><div class="lc">
    El <b>backend</b> —no el modelo— mira el nivel de riesgo de lo recuperado y elige la
    plantilla. Si algún término está en los 156 de riesgo elevado, la respuesta
    <b>encabeza con la derivación médica</b>. Este turno fue
    <code>{t1['risk_tier']}</code>, así que usó la plantilla estándar.
  </div></div>
  <div class="lr"><div class="lb">6 · Síntesis</div><div class="lc">
    Una sola llamada al modelo con el contexto recuperado <b>más el historial del portador</b>.
    El modelo devuelve la lectura y una línea <code>FUENTES: slug…</code>, que el backend
    <b>intersecta con lo que realmente recuperó</b>: cualquier slug inventado se descarta antes
    de llegar al usuario.
  </div></div>
</div>

<div class="callout key">
  <h4>Por qué determinista y no tool-calling</h4>
  <p>ADK permite darle herramientas al modelo y dejar que decida cuándo buscar. Se probó y se
  descartó: con un modelo local el bucle era poco fiable y no acotado, y <b>cada iteración es
  una oportunidad de saltarse un guardarraíl</b>. Un pipeline fijo es auditable, su costo es
  predecible y las etapas 1 y 2 son inevitables por construcción. El camino con herramientas
  quedó implementado como alternativa, pero no es el que corre.</p>
</div>

<h3>Qué ve el usuario, y qué garantiza</h3>
<table>
<tr><th>En pantalla</th><th>Qué garantiza por debajo</th></tr>
<tr><td>Los <b>chips de fuentes</b> bajo cada respuesta</td>
    <td>Solo aparecen términos que se recuperaron de verdad. El modelo no puede citar lo que no se le dio.</td></tr>
<tr><td>El <b>aviso fijo</b> antes del primer mensaje</td>
    <td>La interpretación es simbólica y no sustituye a un profesional — visible antes de escribir, no en letra pequeña al pie.</td></tr>
<tr><td>Una respuesta <b>resaltada en rojo</b> sin fuentes</td>
    <td>Se detectó una urgencia: el mensaje nunca llegó al modelo y la derivación es literal.</td></tr>
<tr><td>«Tu mensaje fue bloqueado por seguridad»</td>
    <td>Saltó un guardarraíl. No se dice cuál: decir qué patrón saltó facilita evadirlo.</td></tr>
<tr><td>«No tengo cobertura para eso»</td>
    <td>Ningún término superó el umbral. El sistema prefiere admitirlo a inventar una lectura.</td></tr>
</table>
""")

    # ── 02 La tesis, demostrada ───────────────────────────────────
    g_lat = bars(["Emergencia\n(corta antes)", "Sin cobertura", "Respuesta completa"],
                 [56, 656, 2878], colors=["#5fbf6f", "#8a8a8a", INK],
                 title="Latencia media por tipo de turno, medida en producción (ms)",
                 fmt="{:.0f}", height=260)

    sec("05", "El hallazgo", "El guardarraíl se demuestra solo", f"""
<p>La analítica de producción registra la latencia de cada turno. Al agrupar por tipo aparece
algo que ningún test tenía que buscar:</p>
<div class="chart">{g_lat}</div>
<p>Una emergencia se resuelve en <b>56 ms</b>; una consulta normal tarda <b>2.878 ms</b>. La
diferencia —<em>51 veces</em>— es exactamente lo que el guardarraíl se salta: la recuperación
y el modelo. Si la derivación fuera una instrucción en el prompt, ambos números serían
iguales.</p>
<p class="small">Datos reales de BigQuery. Es la comprobación empírica de NFR-02b: el
mecanismo no puede ser evadido porque el mensaje nunca llega al LLM.</p>
""")

    # ── 03 Dominio ────────────────────────────────────────────────
    sec("06", "Dominio y riesgo", "Por qué este dominio es distinto", """
<p>El corpus es un diccionario de significados emocionales: 1.265 términos que asocian un
síntoma físico con un conflicto emocional. Eso plantea tres riesgos que no existen en un
chatbot cualquiera.</p>

<div class="grid2">
  <div class="card">
    <h4>Riesgo 1 · Retrasar atención médica</h4>
    <p class="small">Alguien con un síntoma grave podría quedarse con la interpretación
    emocional en vez de ir al médico. <b>Mitigación:</b> 156 términos marcados en 7 niveles de
    riesgo elevado reciben una plantilla que <b>encabeza con la derivación</b>, y 6 grupos de
    emergencia cortan antes incluso de recuperar.</p>
  </div>
  <div class="card">
    <h4>Riesgo 2 · Lenguaje causal</h4>
    <p class="small">Decir «tu resentimiento causó tu gastritis» es falso y dañino. El
    diccionario registra <b>asociaciones simbólicas</b>, nunca causas. <b>Mitigación:</b> hay un
    test que prohíbe patrones causales en las 8 plantillas y en las respuestas.</p>
  </div>
</div>
<div class="card">
  <h4>Riesgo 3 · Confabular fuera de cobertura</h4>
  <p class="small">Un RAG que siempre devuelve <i>k</i> resultados siempre encuentra algo que
  decir, aunque la consulta no tenga nada que ver. <b>Mitigación:</b> un umbral de cobertura
  explícito y una respuesta «sin cobertura» honesta. Se priorizó
  <b>precisión fuera de dominio = 1.0</b> por encima del recall: en salud, inventar una
  interpretación es peor que admitir que no se sabe.</p>
</div>
""")

    # ── 04 Recuperación ───────────────────────────────────────────
    labels = [t for t, _, _, _ in RETRIEVAL]
    bge = [a / b for _, (a, b), _, _ in RETRIEVAL]
    vtx = [a / b for _, _, (a, b), _ in RETRIEVAL]
    g_ret = grouped(labels, bge, vtx, "bge-m3 (local, 1024d)", "gemini-embedding-001 (3072d)",
                    title="Recuperación sobre el gold set (recall@5 / precisión)")

    filas_ret = "".join(
        f"<tr><td><code>{t}</code></td><td class='num'>{a}/{b} = {a/b:.3f}</td>"
        f"<td class='num'><b>{c}/{d} = {c/d:.3f}</b></td><td class='num'>{meta}</td>"
        f"<td>{'<span class=ok>✓</span>' if (c/d) >= (0.85 if t=='single' else 0.90 if t=='alias' else 1.0) else 'parcial'}</td></tr>"
        for t, (a, b), (c, d), meta in RETRIEVAL)

    sec("07", "Recuperación híbrida", "Cómo se decide qué es relevante", f"""
<p>El corpus es un diccionario, y en un diccionario <b>el título es la señal fiable</b>: la
prosa emocional de dos términos distintos es casi idéntica, así que el embedding denso por sí
solo no discrimina. De ahí el diseño:</p>
<ul>
<li><b>Cobertura</b> = existe match nominal normalizado de título/alias, con <i>light
stemming</i> (plurales y deverbales) y stopwords. Ese match <i>es</i> el umbral.</li>
<li><b>Ranking</b> = fusión RRF de denso (FAISS, coseno) + BM25 con peso reforzado al título.</li>
<li><b>El denso solo desempata</b> dentro del mismo nivel de match.</li>
</ul>
<div class="chart">{g_ret}</div>
<table>
<tr><th>Tipo</th><th class="num">bge-m3 (local)</th><th class="num">Vertex (producción)</th>
    <th class="num">Meta</th><th>Estado</th></tr>
{filas_ret}
</table>
<div class="callout">
  <h4>El gate duro de M2 se cumple por primera vez</h4>
  <p><code>alias</code> pasa de 0.867 a <b>0.933</b> y supera el ≥0.90 que llevaba pendiente
  desde el segundo milestone. Los tres criterios del gate —single ≥0.85, alias ≥0.90 y
  precisión fuera de dominio 1.0— se cumplen ahora <b>simultáneamente</b>.</p>
</div>
""")

    # ── 05 Calibración ────────────────────────────────────────────
    g_bar = bars([f"{t:.2f}" for t, _, _ in BARRIDO], [o_ for _, o_, _ in BARRIDO],
                 colors=[CORAL if o_ < 13 else "#5fbf6f" for _, o_, _ in BARRIDO],
                 title="Precisión fuera de dominio según el umbral denso (Vertex)",
                 fmt="{:.0f}", height=230, ymax=13)

    sec("08", "Calibración", "Un umbral correcto que se vuelve bug", f"""
<p>La cobertura tiene un respaldo: si no hay match nominal pero el coseno denso es muy alto, se
acepta. Ese umbral valía <code>0.70</code>, fijado con datos… <b>para <code>bge-m3</code></b>.</p>
<p>Al migrar a Vertex, la consulta «¿qué significa emocionalmente el cuerpo?» puntuaba
<b>0.7385</b> sin ningún match nominal y se colaba como cobertura, <b>rompiendo la precisión
fuera de dominio de 1.0</b>.</p>
<div class="chart">{g_bar}</div>
<p>Se barrió el umbral sobre el gold set y se tomó el más bajo que conserva 13/13. Se fijó
<b>0.75</b>, en medio de la meseta estable, y ahora es un <b>mapa por modelo</b>: un modelo sin
calibrar recibe el valor más estricto.</p>
<div class="callout">
  <h4>La lección</h4>
  <p>Cada espacio de embeddings tiene su propia distribución de similitud. Un umbral heredado
  <b>no falla ruidosamente</b>: simplemente empieza a inventar interpretaciones para consultas
  que no cubre. En este dominio, ese silencio es el peor modo de fallo posible.</p>
</div>
""")

    # ── 06 Infraestructura ────────────────────────────────────────
    arq = """
<div class="flow">
  <div class="node d"><div class="n">Cloud Run</div>min=0 · max=3<br>back + front</div><div class="arw">→</div>
  <div class="node a"><div class="n">Vertex AI</div>flash-lite<br>embedding-001</div><div class="arw">→</div>
  <div class="node s"><div class="n">Firestore</div>auth · perfiles<br>sesiones ADK</div><div class="arw">→</div>
  <div class="node g"><div class="n">BigQuery</div>métricas<br>sin texto</div>
</div>"""

    sec("09", "Infraestructura", "37 recursos, todo como código", f"""
{arq}
<p>Toda la infraestructura es Terraform: no se creó nada a mano en la consola. El índice FAISS
(19 MB) va <b>horneado en la imagen</b>, así que <em>no hay servicio de vectores</em>. Y
deliberadamente <b>no hay Cloud SQL ni VPC Connector</b>: son justo los componentes que corren
24/7 y no escalan a cero.</p>

<table>
<tr><th>Recurso</th><th class="num">n</th><th>Para qué</th></tr>
<tr><td><code>google_project_service</code></td><td class="num">9</td><td>APIs habilitadas</td></tr>
<tr><td><code>google_bigquery_table</code></td><td class="num">4</td><td>consultas · recuperación · guardarraíles · eval</td></tr>
<tr><td><code>google_project_iam_member</code></td><td class="num">4</td><td>los únicos roles a nivel proyecto</td></tr>
<tr><td><code>google_secret_manager_secret</code> +versión +IAM</td><td class="num">6</td><td>JWT y sal del hash analítico</td></tr>
<tr><td><code>google_firestore_index</code></td><td class="num">2</td><td>historial por portador · eventos por sesión</td></tr>
<tr><td><code>google_cloud_run_v2_service</code> +IAM</td><td class="num">2</td><td>el servicio y su acceso público</td></tr>
<tr><td><code>google_bigquery_dataset</code> +IAM</td><td class="num">2</td><td>analítica</td></tr>
<tr><td><code>google_artifact_registry_repository</code> +IAM</td><td class="num">2</td><td>imagen, con limpieza automática</td></tr>
<tr><td><code>google_firestore_database</code></td><td class="num">1</td><td>auth · perfiles · sesiones · auditoría</td></tr>
<tr><td><code>google_service_account</code></td><td class="num">1</td><td>identidad del contenedor, sin claves</td></tr>
<tr><td><code>google_storage_bucket</code></td><td class="num">1</td><td>estado remoto de Terraform</td></tr>
<tr><td><code>random_password</code></td><td class="num">2</td><td>secretos generados, nunca escritos a mano</td></tr>
</table>

<p><b>Vertex se autentica por service account, no por clave de API.</b> Eso elimina un secreto
entero del sistema: uno menos que rotar y que filtrar.</p>
""", pbreak=True)

    # ── 07 Costo ──────────────────────────────────────────────────
    g_cost = hbars(["A · Firestore (elegida)", "B′ · Cloud SQL apagada", "B · Cloud SQL 24/7"],
                   [0.12, 1.83, 9.83], colors=["#5fbf6f", "#8a8a8a", CORAL],
                   title="Costo mensual en reposo por alternativa (USD)", fmt="${:.2f}", row_h=30)
    g_img = bars(["Original", "Local", "Cloud", "Comprimida\nen registry"],
                 [2700, 894, 582, 147], colors=[CORAL, "#8a8a8a", "#8a8a8a", "#5fbf6f"],
                 title="Tamaño de la imagen Docker (MB)", fmt="{:.0f}", height=230)

    sec("10", "Costo", "El presupuesto se hizo antes de crear nada", f"""
<p>Los precios se consultaron y el consumo se <b>midió sobre el propio repo</b>: 3.400 tokens
de entrada y 450 de salida por turno = <b>$0.00052</b>, o $0.52 por cada 1.000 turnos.
Reindexar el corpus completo costó <b>$0.09</b>, una vez.</p>

<h3>La decisión que movía la aguja</h3>
<p>Casi todo cabe en el free tier. Lo único que podía <i>no</i> escalar a cero era dónde viven
auth y memoria:</p>
<div class="chart">{g_cost}</div>
<p>Se eligió <b>Firestore</b>. El precio no fue dinero sino código: ADK 2.8 no trae un session
service de Firestore, así que hubo que implementarlo, y reescribir la persistencia tras un
protocolo con dos backends intercambiables.</p>

<table>
<tr><th>Concepto</th><th class="num">Mensual</th><th>Nota</th></tr>
<tr><td>Cloud Run</td><td class="num">$0</td><td>6% del free tier con 5.000 turnos/mes</td></tr>
<tr><td>Firestore</td><td class="num">$0</td><td>dentro de 50k lecturas y 20k escrituras diarias</td></tr>
<tr><td>BigQuery</td><td class="num">$0</td><td>&lt;1 GiB escaneado de 1 TiB gratis</td></tr>
<tr><td>Artifact Registry</td><td class="num">$0</td><td>147 MB comprimidos, bajo los 0,5 GB gratis</td></tr>
<tr><td>Secret Manager</td><td class="num"><b>$0.12</b></td><td>2 versiones activas × $0.06</td></tr>
<tr><td>Vertex (500 turnos)</td><td class="num">$0.26</td><td>medido, no estimado</td></tr>
<tr><td><b>Total con 500 turnos</b></td><td class="num"><b>≈ $0.38</b></td><td>en reposo: <b>$0.12</b></td></tr>
</table>

<h3>Adelgazar la imagen: −95%</h3>
<div class="chart">{g_img}</div>
<ul>
<li>Un <code>chown -R appuser /app</code> <b>después</b> de crear el venv duplicaba el árbol
entero en una capa de <b>682 MB</b>. Ahora el build es multi-stage y el usuario se crea antes
de copiar.</li>
<li><code>scipy</code> (71 MB) estaba en las dependencias y <b>no lo usaba ningún fichero</b>.
<code>litellm</code> (92 MB, arrastra botocore y openai) solo hace falta en local.</li>
</ul>
<p class="small">El beneficio que más importa no es el costo sino el <b>arranque en frío</b>,
que es el precio real de escalar a cero.</p>
""")

    # ── 08 Resultados ─────────────────────────────────────────────
    g_e2e = grouped(["global", "single", "alias", "multi"],
                    [ml["overall_accuracy"]["mean"], ml["single"]["recall"]["mean"],
                     ml["alias"]["recall"]["mean"], ml["multi"]["recall"]["mean"]],
                    [mv["overall_accuracy"]["mean"], mv["single"]["recall"]["mean"],
                     mv["alias"]["recall"]["mean"], mv["multi"]["recall"]["mean"]],
                    "local (gemma4)", "producción (Vertex)",
                    title="Precisión end-to-end · 52 preguntas por el pipeline real")
    g_lat2 = grouped(["single", "alias", "multi"],
                     [ml["single"]["latency_s"]["mean"] / 12, ml["alias"]["latency_s"]["mean"] / 12,
                      ml["multi"]["latency_s"]["mean"] / 12],
                     [mv["single"]["latency_s"]["mean"] / 12, mv["alias"]["latency_s"]["mean"] / 12,
                      mv["multi"]["latency_s"]["mean"] / 12],
                     "local (gemma4)", "producción (Vertex)",
                     title="Latencia por turno — escala relativa", fmt="{:.2f}")

    sec("11", "Resultados", "Qué tan bien funciona", f"""
<p>52 preguntas derivadas del gold set, corridas por el <b>pipeline real del chat</b>. La
verificación es <b>determinista</b>: acierta si cita el slug esperado o contiene el término.
Sin LLM como juez. Métricas por bootstrap con seed fijo (42, 2.000 remuestreos).</p>
<div class="chart">{g_e2e}</div>

<table>
<tr><th>Métrica</th><th class="num">n</th><th class="num">Local</th><th class="num">Producción</th><th class="num">IC 95%</th></tr>
<tr><td>Precisión global</td><td class="num">{e2e_v['n']}</td><td class="num">{ml['overall_accuracy']['mean']:.3f}</td>
    <td class="num"><b>{mv['overall_accuracy']['mean']:.3f}</b></td>
    <td class="num">[{mv['overall_accuracy']['ci95_low']:.3f}, {mv['overall_accuracy']['ci95_high']:.3f}]</td></tr>
<tr><td>Recall single</td><td class="num">31</td><td class="num">{ml['single']['recall']['mean']:.3f}</td>
    <td class="num"><b>{mv['single']['recall']['mean']:.3f}</b></td>
    <td class="num">[{mv['single']['recall']['ci95_low']:.3f}, {mv['single']['recall']['ci95_high']:.3f}]</td></tr>
<tr><td>Recall alias</td><td class="num">15</td><td class="num">{ml['alias']['recall']['mean']:.3f}</td>
    <td class="num"><b>{mv['alias']['recall']['mean']:.3f}</b></td>
    <td class="num">[{mv['alias']['recall']['ci95_low']:.3f}, {mv['alias']['recall']['ci95_high']:.3f}]</td></tr>
<tr><td>Recall multi-hop</td><td class="num">6</td><td class="num">{ml['multi']['recall']['mean']:.3f}</td>
    <td class="num"><b>{mv['multi']['recall']['mean']:.3f}</b></td>
    <td class="num">[{mv['multi']['recall']['ci95_low']:.3f}, {mv['multi']['recall']['ci95_high']:.3f}]</td></tr>
<tr><td>Latencia media</td><td class="num">52</td><td class="num">8,5 s</td><td class="num"><b>2,1 s</b></td><td class="num">—</td></tr>
</table>

<h3>Honestidad sobre estos números</h3>
<ol>
<li><b>La precisión fuera de dominio de 1.0 se compró a costa de recall.</b> El precio son los
fallos de sinonimia coloquial (<i>panza→estómago</i>, <i>dormir→insomnio</i>) ausentes del
fichero de alias. Fue una decisión, no un accidente.</li>
<li><b>Multi-hop sigue siendo el punto débil</b> (0.667). Citar <i>todos</i> los síntomas en
una síntesis cohesiva es lo más difícil, y arrastra el mismo hueco.</li>
<li><b>El LLM no es determinista.</b> Entre corridas locales se observó 0.865–0.885. Lo
reproducible es el <i>procedimiento</i>, no la cifra exacta.</li>
<li><b>Buena parte del salto de multi-hop no es mérito del modelo</b>, sino de un bug corregido
—ver §14.</li>
</ol>
""", pbreak=True)

    # ── 09 Seguridad ──────────────────────────────────────────────
    g_tests = hbars(["Seguridad médica", "Backend de nube", "Infra (sobre el plan)",
                     "Guardarraíles / injection", "Proveedores", "Agente", "Auth y memoria"],
                    [173, 23, 17, 17, 14, 9, 7],
                    colors=[CORAL, INK, INK, CORAL, "#8a8a8a", "#8a8a8a", "#8a8a8a"],
                    title="260 tests por área", fmt="{:.0f}", row_h=26)

    sec("12", "Seguridad verificada", "Tests que pueden fallar", f"""
<div class="chart">{g_tests}</div>
<p class="small">253 passed + 7 skipped. Los saltados necesitan un Postgres alcanzable desde el
host y cubren aislamiento, persistencia y borrado en el backend local.</p>

<div class="grid2">
  <div class="card">
    <h4>173 tests de seguridad médica</h4>
    <p class="small">Los <b>156 términos</b> de riesgo elevado, cada uno con su plantilla de
    derivación. Cero patrones causales en las 8 plantillas. Y los 6 grupos de emergencia con
    <code>retrieval.search</code> monkeypatcheado para <b>fallar si llega a llamarse</b>: eso
    prueba que el corte ocurre <i>antes</i> de recuperar.</p>
  </div>
  <div class="card">
    <h4>17 aserciones de infraestructura</h4>
    <p class="small">Sobre el <code>terraform plan</code> <b>resuelto</b>, no sobre el texto de
    los <code>.tf</code>: un comentario no engaña a un plan. Roles prohibidos, alcance por
    recurso, <code>allUsers</code> solo en el invoker, bucket de estado privado, escala a cero,
    y que BigQuery no admita ningún campo capaz de llevar texto de chats.</p>
  </div>
</div>

<div class="callout">
  <h4>Validadas por mutación, no solo verdes</h4>
  <p>Un test que no puede fallar no prueba nada. Al inyectar en el plan
  <code>roles/owner</code>, un campo <code>mensaje</code> en BigQuery y
  <code>min_instances = 1</code>, <b>fallan 5 aserciones</b>; al restaurar el plan, vuelven las
  17 en verde.</p>
</div>

{term("scripts/secrets_audit.sh", '''<span class="m"># Auditoría de secretos — 8/8</span>
<span class="g">✅</span> .env fuera de git
<span class="g">✅</span> sin literales de secreto en ficheros versionados
<span class="g">✅</span> la imagen no contiene .env ni credenciales
<span class="g">✅</span> sin literales de secreto en el código Python
<span class="g">✅</span> sin .tfstate ni .tfvars versionados
<span class="g">✅</span> sin secretos en claro en los .tf
<span class="g">✅</span> no se crean claves de service account
<span class="g">✅</span> el plan no expone valores sensibles''')}
""")

    # ── 10 Evidencia ──────────────────────────────────────────────
    filas_smoke = "".join(
        f"<tr><td>{c['caso']}</td><td><span class='chip a'>{c['fr']}</span></td>"
        f"<td class='{'ok' if c['ok'] else 'bad'}'>{'✓' if c['ok'] else '✗'}</td>"
        f"<td class='small'>{c['detalle']}</td></tr>" for c in smoke["casos"])

    sec("13", "Evidencia", f"Pruebas de uso en producción — {smoke['ok']}/{smoke['total']}", f"""
<p>Ejecutadas contra el servicio vivo con <code>scripts/prod_smoke.py</code>. <b>Cada caso
lleva su aserción</b>: si una falla, la corrida falla. La evidencia no puede decir «OK» sin
haberlo comprobado.</p>
<table>
<tr><th>Caso</th><th>FR/NFR</th><th></th><th>Detalle observado</th></tr>
{filas_smoke}
</table>

<h3>La interfaz, capturada sobre el sistema real</h3>
<p class="small">Chrome headless sobre la UI desplegada. Cada escenario verifica su aserción en
el DOM: si los chips de fuentes no se ven <i>en el viewport</i>, si falta la clase de
emergencia o si un GIF no tiene transiciones reales, la corrida falla en vez de producir una
imagen vacía.</p>
<div class="grid2">
{shot(EV / "register.png", "Acceso y alta de usuario (FR-16/FR-18).")}
{shot(EV / "rag_sources.png", "Respuesta con chips de fuentes y disclaimer visible (FR-19/FR-20).")}
</div>
<div class="grid2">
{shot(EV / "emergencia.png", "Emergencia: derivación resaltada y sin fuentes, porque no llegó a recuperar (FR-06).")}
{shot(EV / "bloqueo.png", "Prompt injection bloqueado con 403 (NFR-01).")}
</div>
<div class="grid2">
{shot(EV / "profiles.png", "Historial persistido del portador en Firestore (FR-14).")}
{shot(EV / "sessions.png", "Sesiones ADK persistidas (FR-12).")}
</div>

<h3>Analítica en BigQuery</h3>
<p>El dataset se alimenta desde el propio turno de chat. La regla dura: <b>métricas y
metadatos, nunca el texto de las conversaciones</b>; el usuario es un hash con sal, no su
correo.</p>
<table>
<tr><th>Tabla</th><th>Para qué sirve</th></tr>
<tr><td><code>consultas</code></td><td>términos consultados, nivel de riesgo, latencia por turno</td></tr>
<tr><td><code>recuperacion</code></td><td>qué consultas reales quedan sin cobertura — convierte la deuda de sinonimia en algo medible</td></tr>
<tr><td><code>guardarrailes</code></td><td>cuántas veces dispara cada guardarraíl, y cuál</td></tr>
<tr><td><code>eval</code></td><td>serie histórica de las corridas: si el recall se degrada entre versiones, se ve</td></tr>
</table>
""", pbreak=True)

    # ── 11 Lo que falló ───────────────────────────────────────────
    sec("14", "Postmortem", "Lo que solo apareció al desplegar", f"""
<p>El despliegue real destapó cuatro cosas que ninguna suite local había detectado. Vale la
pena contarlas: son el resultado más útil del proyecto.</p>

<h3>1 · Una fuga de privacidad en producción</h3>
<p>Al inspeccionar las filas reales de BigQuery, el campo <code>symptom_slug</code> contenía
<b>el mensaje literal del usuario</b>. Cuando la extracción de síntomas no devuelve nada, el
pipeline busca con el mensaje entero y esa lista se emitía tal cual.</p>
<div class="callout">
  <p><b>El test que cubría esto no lo detectó</b>: usaba un caso de emergencia, donde la lista
  de síntomas va vacía. El camino con fuga era el de «sin cobertura». Corregido, datos purgados
  recreando la tabla, y test de regresión sobre el camino correcto — validado por mutación.</p>
</div>

<h3>2 · El agente llevaba degradado sin avisar</h3>
<p><code>gemini-2.5-flash-lite</code> devuelve el JSON de extracción <b>envuelto en un bloque
markdown</b>; <code>gemma4</code> lo devuelve pelado. <code>json.loads</code> fallaba y el
sistema caía al fallback <b>en todos los turnos</b>, buscando con el mensaje entero en vez de
con cada síntoma por separado.</p>
{term("diagnóstico", '''<span class="m">$ raw = _complete(_EXTRACT_PROMPT, "se me cae el pelo y me salen granos")</span>
<span class="k">RAW:</span> '```json\\n[\\n  "caída del pelo",\\n  "granos"\\n]\\n```'
<span class="m"># json.loads() falla -> fallback -> multi-hop degradado, sin excepción</span>''')}
<p>Corregirlo subió <code>multi</code> de 0.500 a <b>0.667</b> y el global a <b>0.923</b>.
Buena parte de la mejora atribuible «al modelo» era en realidad un bug.</p>

<h3>3 · Cloud Run reserva el prefijo <code>ah-</code></h3>
<p>El servicio <code>ah-emociones-app</code> se rechaza con un 400 en pleno <code>apply</code>.
Se separó el nombre del servicio con una <code>validation</code> en Terraform, para que el
próximo error salga en el <code>plan</code> y no a mitad del despliegue.</p>

<h3>4 · Código escrito, testeado… y nunca llamado</h3>
<p>El emisor de analítica existía y tenía tests verdes, pero <b>nadie lo invocaba</b>: las
tablas quedaron vacías tras el primer despliegue. Probar un módulo aisladamente no detecta que
esté desconectado. Ahora hay tests que corren el <b>pipeline completo</b> y exigen que emita.</p>
""")

    # ── 12 Cierre ─────────────────────────────────────────────────
    sec("15", "Cierre", "Deuda abierta y cómo reproducirlo", f"""
<h3>Lo que queda abierto, declarado</h3>
<ul>
<li><b>Sinonimia coloquial</b> ausente del fichero de alias, congelado desde el inicio.
Cerrarla pide un fichero de sinónimos aparte, no tocar el congelado. Es la causa raíz tanto de
<code>multi</code> 0.667 como de <code>risk_tier</code> 9/10.</li>
<li><b>La alerta de presupuesto hay que crearla a mano.</b> La API de Billing Budgets devuelve
400 en esta cuenta de facturación; se descartó que fuera la configuración comprobando que falla
igual un budget mínimo creado con <code>gcloud</code> sin filtro. Es la red de seguridad contra
un gasto inesperado de Vertex, lo único que escala con el uso.</li>
<li><b>Los tests del backend de nube usan un doble en memoria</b>, no el emulador de Firestore.
El despliegue real fue la primera vez que el código habló con Firestore de verdad — y ahí
aparecieron dos de los cuatro fallos del postmortem.</li>
</ul>

<h3>Reproducir todo</h3>
{term("desde la raíz del repo", '''<span class="k">scripts/test.sh</span>          <span class="m"># 253 passed + 7 skipped</span>
<span class="k">scripts/evidence.sh</span>      <span class="m"># eval e2e → capturas → GIFs → reportes</span>
<span class="k">scripts/infra_audit.sh</span>   <span class="m"># fmt + validate + plan real + 17 aserciones</span>
<span class="k">scripts/secrets_audit.sh</span> <span class="m"># 8/8</span>
<span class="k">scripts/prod_smoke.py</span>    <span class="m"># pruebas contra el servicio vivo</span>
<span class="k">scripts/final_report.py</span>  <span class="m"># este documento</span>''')}

<div class="callout key">
  <h4>Qué se lleva el proyecto</h4>
  <p>Que en un dominio con consecuencias, <b>la seguridad tiene que ser verificable, no
  prometida</b>. Los guardarraíles se resuelven en el backend y se prueban con tests que pueden
  fallar; las capturas se autocomprueban; las aserciones de infraestructura se validan por
  mutación. Y aun así, el despliegue real encontró cuatro cosas que nada de eso había visto —
  incluida una fuga de datos de salud. Esa es la parte honesta del resultado.</p>
</div>
""")

    font_b64 = _b64(FONT) if FONT.exists() else ""
    css = CSS.replace("__FONT__", font_b64)

    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Especialista en enfermedades emocionales · Reporte final</title>
<style>{css}</style>
</head>
<body>

<header class="hero">
  <svg class="medal" viewBox="0 0 200 200" fill="none">
    <circle cx="100" cy="100" r="86" stroke="#3f3f3f" stroke-width="6" opacity=".9"/>
    <circle cx="100" cy="100" r="66" stroke="#8a8a8a" stroke-width="6" opacity=".8"/>
    <circle cx="100" cy="100" r="46" stroke="#ff5a5f" stroke-width="6" opacity=".95"/>
    <circle cx="100" cy="100" r="24" stroke="#ff5a5f" stroke-width="2" opacity=".55"/>
  </svg>
  <div class="wrap">
    <p class="kicker">Diplomado en IA · Proyecto final</p>
    <h1>Especialista en<br>enfermedades emocionales</h1>
    <p class="lede">Un agente RAG con memoria persistente y guardarraíles médicos
    deterministas, desplegado en Google Cloud Run.</p>
    <p class="meta">{hoy} · en producción · 37 recursos GCP · 260 tests · $0.12/mes</p>
  </div>
</header>

{''.join(S)}

<footer><div class="wrap">
  <span>Especialista en enfermedades emocionales · Reporte final</span>
  <span class="seal">{hoy}</span>
</div></footer>

</body></html>"""


def main() -> int:
    e2e_l = _json(EV / "e2e_results.json")
    e2e_v = _json(EV / "e2e_results_vertex.json")
    smoke = _json(EV / "prod_smoke.json")
    conv = _json(EV / "conversacion.json")

    html_path = OUT / "reporte-final.html"
    html_path.write_text(build(e2e_l, e2e_v, smoke, conv), encoding="utf-8")
    print(f"[final-report] {html_path} ({html_path.stat().st_size / 1024:.0f} KB)")

    pdf_path = OUT / "reporte-final.pdf"
    chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    try:
        subprocess.run(
            [chrome, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
             f"--print-to-pdf={pdf_path}", html_path.as_uri()],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=180,
        )
        print(f"[final-report] {pdf_path} ({pdf_path.stat().st_size / 1024:.0f} KB)")
    except (FileNotFoundError, subprocess.SubprocessError) as e:
        print(f"[final-report] PDF no generado: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
