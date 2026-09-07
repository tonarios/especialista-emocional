"""Captura una conversación real en producción, anotada turno a turno.

No es un test: es el material para explicar **cómo funciona el sistema**. Recorre
el ciclo completo de una persona —registro, varias consultas, una pregunta sobre
su propio historial— y en cada turno registra qué pasó por dentro:

  · qué camino tomó el turno (respuesta / emergencia / bloqueado / sin cobertura)
  · qué términos citó, y con qué nivel de riesgo
  · cuánto tardó
  · **cómo quedó la memoria después**: el perfil y los eventos de la sesión ADK

Así se ve la relación entre identidad (JWT), aislamiento y memoria: el mismo
`user_id` que sale del token es la clave del perfil, del documento de Firestore
y de la sesión de ADK.

Uso: uv run python scripts/capture_conversation.py [--url https://...]
Salida: outputs/evidence/conversacion.json
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs" / "evidence" / "conversacion.json"
URL = "https://emociones-app-zxzgilzqfq-uc.a.run.app"

# Guion de una consulta realista: dos síntomas en turnos distintos, y luego una
# pregunta sobre el propio historial. El tercer turno solo puede responderse si
# la memoria funciona.
GUION = [
    ("me duele la garganta muy seguido y me cuesta decir lo que pienso",
     "Primera consulta. El agente extrae el síntoma, recupera del diccionario y "
     "cita solo lo que recuperó."),
    ("también he tenido dolores de espalda baja estas semanas",
     "Segunda consulta, misma sesión. El historial del turno anterior ya viaja "
     "en el contexto de la síntesis."),
    ("¿cuál fue mi última consulta?",
     "Pregunta sobre la propia memoria. No se recupera del diccionario: se "
     "responde desde el historial persistido del portador."),
]


def _req(url, *, method="GET", body=None, token=None, timeout=120):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def _chat(base, token, message, session):
    t0 = time.perf_counter()
    st, raw = _req(f"{base}/chat", method="POST", token=token,
                   body={"message": message, "session_id": session})
    dt = time.perf_counter() - t0
    if st == 403:
        return {"kind": "blocked", "http": 403, "text": json.loads(raw).get("detail", ""),
                "sources": []}, dt
    final = {}
    for line in raw.splitlines():
        if line.strip():
            ev = json.loads(line)
            if ev.get("done"):
                final = ev
    final["http"] = st
    return final, dt


def main(base: str) -> int:
    email = f"demo-{uuid.uuid4().hex[:6]}@ejemplo.co"
    session = "conv-" + uuid.uuid4().hex[:6]
    print(f"[conversación] {base}\n  usuario: {email}\n  sesión:  {session}\n")

    # ── Paso 1: registro. Aquí nace la identidad que todo lo demás usa. ──
    t0 = time.perf_counter()
    st, body = _req(f"{base}/api/register", method="POST",
                    body={"email": email, "password": "clave-segura-123"})
    dt_reg = time.perf_counter() - t0
    token = json.loads(body).get("token", "")
    print(f"  registro: HTTP {st} · token {token[:22]}… ({dt_reg:.1f}s)")

    turnos = []
    for mensaje, nota in GUION:
        r, dt = _chat(base, token, mensaje, session)

        # Estado de la memoria DESPUÉS del turno.
        _, p = _req(f"{base}/profile", token=token)
        perfil = json.loads(p)
        _, s = _req(f"{base}/sessions", token=token)
        sesiones = json.loads(s)["sessions"]
        eventos = sum(x["events"] for x in sesiones)

        turnos.append({
            "usuario": mensaje,
            "nota": nota,
            "kind": r["kind"],
            "risk_tier": r.get("risk_tier"),
            "respuesta": r.get("text", ""),
            "fuentes": [{"slug": f["slug"], "title": f["title"]} for f in r.get("sources", [])],
            "latencia_s": round(dt, 2),
            "memoria_despues": {
                "consultas_en_perfil": len(perfil.get("consultations", [])),
                "eventos_en_sesion": eventos,
                "ultima_entrada": (perfil.get("consultations") or [{}])[-1],
            },
        })
        print(f"  › {mensaje[:52]:52s} → {r['kind']:14s} "
              f"{len(r.get('sources', []))} fuentes · {dt:.1f}s · "
              f"perfil={len(perfil.get('consultations', []))} eventos={eventos}")

    # ── Aislamiento: un segundo usuario no ve nada de lo anterior. ──
    otro = f"otra-{uuid.uuid4().hex[:6]}@ejemplo.co"
    _req(f"{base}/api/register", method="POST", body={"email": otro, "password": "clave-segura-123"})
    _, b = _req(f"{base}/api/login", method="POST",
                body={"email": otro, "password": "clave-segura-123"})
    token_b = json.loads(b).get("token", "")
    _, pb = _req(f"{base}/profile", token=token_b)
    _, sb = _req(f"{base}/sessions", token=token_b)
    aislamiento = {
        "usuario_b": otro,
        "consultas_visibles": len(json.loads(pb).get("consultations", [])),
        "sesiones_visibles": len(json.loads(sb)["sessions"]),
    }
    print(f"\n  aislamiento: B ve {aislamiento['consultas_visibles']} consultas y "
          f"{aislamiento['sesiones_visibles']} sesiones (debe ser 0 y 0)")

    # ── Y sin token no se ve nada en absoluto. ──
    st_sin, _ = _req(f"{base}/profile")
    print(f"  sin token: HTTP {st_sin} (debe ser 401)")

    payload = {
        "url": base, "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "usuario": email, "session_id": session,
        "registro": {"http": st, "latencia_s": round(dt_reg, 2),
                     "token_prefijo": token[:22] + "…"},
        "turnos": turnos,
        "aislamiento": aislamiento,
        "sin_token_http": st_sin,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n[conversación] {OUT}")

    ok = (aislamiento["consultas_visibles"] == 0 and aislamiento["sesiones_visibles"] == 0
          and st_sin == 401 and all(t["kind"] != "blocked" for t in turnos))
    return 0 if ok else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=URL)
    raise SystemExit(main(ap.parse_args().url))
