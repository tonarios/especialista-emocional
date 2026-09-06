"""Capturas de evidencia M8 vía Chrome DevTools Protocol (CDP, sin Playwright).

Genera en `outputs/evidence/`:
  - register.png    : pantalla de acceso (login/registro).
  - rag_sources.png : respuesta RAG con chips de fuentes visibles.
  - profiles.png    : historial de consultas persistido (via /profile).
  - sessions.png    : sesiones ADK (via /sessions).

Uso:
  scripts/capture_evidence.py [--base http://localhost:8000]
Requisito: Google Chrome instalado (macOS path) y la app corriendo.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import random
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import websockets

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs" / "evidence"

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
DEBUG_PORT = 9222

BASE = "http://localhost:8000"
EMAIL = f"evidencia-{random.randrange(10**8)}@demo.co"
PASSWORD = "clave-segura-123"


def _launch_chrome() -> subprocess.Popen:
    return subprocess.Popen(
        [
            CHROME, "--headless=new", f"--remote-debugging-port={DEBUG_PORT}",
            "--user-data-dir=/tmp/ah-emociones-chrome", "--no-first-run",
            "--disable-gpu", "--window-size=900,1000", "about:blank",
        ],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def _page_ws(retries: int = 20) -> str:
    for _ in range(retries):
        try:
            with urllib.request.urlopen(f"http://localhost:{DEBUG_PORT}/json") as r:
                for p in json.loads(r.read()):
                    if p.get("type") == "page":
                        return p["webSocketDebuggerUrl"]
        except Exception:
            time.sleep(0.5)
    raise RuntimeError("no se encontró un target page en CDP")


async def main(base: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    chrome = _launch_chrome()
    try:
        ws_url = _page_ws()
    except RuntimeError:
        chrome.terminate()
        print("[capture] no se pudo arrancar Chrome/CDP", file=sys.stderr)
        sys.exit(1)

    async with websockets.connect(ws_url, max_size=50 * 1024 * 1024) as ws:
        _id = 0

        async def cmd(method, params=None):
            nonlocal _id
            _id += 1
            await ws.send(json.dumps({"id": _id, "method": method, "params": params or {}}))
            while True:
                msg = json.loads(await ws.recv())
                if msg.get("id") == _id:
                    if "error" in msg:
                        raise RuntimeError(f"{method}: {msg['error']}")
                    return msg.get("result", {})

        async def evaluate(expr, await_promise=False):
            r = await cmd("Runtime.evaluate",
                          {"expression": expr, "returnByValue": True, "awaitPromise": await_promise})
            return r.get("result", {}).get("value")

        async def shot(name):
            r = await cmd("Page.captureScreenshot", {"format": "png"})
            (OUT / name).write_bytes(base64.b64decode(r["data"]))
            print(f"  [capture] {name}")

        await cmd("Page.enable")
        await cmd("Runtime.enable")

        # 1. Pantalla de acceso (login/registro) -> register.png
        await cmd("Page.navigate", {"url": f"{base}/"})
        await asyncio.sleep(3)
        await shot("register.png")

        # 2. Registro real de un usuario nuevo
        await evaluate("document.getElementById('register-btn').click()")  # modo registro
        await asyncio.sleep(0.5)
        await evaluate(
            f"document.getElementById('email').value='{EMAIL}';"
            f"document.getElementById('password').value='{PASSWORD}';"
        )
        await asyncio.sleep(0.5)
        await evaluate("document.getElementById('login-btn').click()")
        await asyncio.sleep(4)
        ok = await evaluate("!document.getElementById('chat-view').hidden")
        print(f"  chat visible tras registro: {ok}")

        # 3. Pregunta RAG -> rag_sources.png (con chips de fuentes)
        await evaluate(
            "document.getElementById('chat-input').value='me duele la garganta a menudo';"
            "document.getElementById('chat-form').dispatchEvent(new Event('submit', {cancelable:true}));"
        )
        # esperar a que surjan chips (.chip)
        chips = 0
        for _ in range(30):
            chips = await evaluate("document.querySelectorAll('.chip').length")
            if chips:
                break
            await asyncio.sleep(2)
        await asyncio.sleep(1)
        await shot("rag_sources.png")
        print(f"  chips visibles: {chips}")

        # 4. Perfil (historial persistido) -> profiles.png
        await evaluate(
            "(async()=>{const t=localStorage.getItem('ah_emociones.token');"
            "const r=await fetch('/profile',{headers:{Authorization:'Bearer '+t}});"
            "const d=await r.json();const p=document.createElement('pre');"
            "p.style.cssText='position:fixed;inset:0;margin:0;padding:24px;background:#0a0a24;"
            "color:#fff;z-index:99999;font:14px monospace;overflow:auto';"
            "p.textContent='PERFIL (GET /profile)\\n\\n'+JSON.stringify(d,null,2);"
            "document.body.appendChild(p);return 'ok';})()",
            await_promise=True,
        )
        await asyncio.sleep(0.5)
        await shot("profiles.png")

        # 5. Sesiones ADK -> sessions.png
        await evaluate("document.body.style.opacity='0'", await_promise=False)
        await evaluate(
            "(async()=>{const t=localStorage.getItem('ah_emociones.token');"
            "const r=await fetch('/sessions',{headers:{Authorization:'Bearer '+t}});"
            "const d=await r.json();const p=document.createElement('pre');"
            "p.style.cssText='position:fixed;inset:0;margin:0;padding:24px;background:#0a0a24;"
            "color:#fff;z-index:99999;font:14px monospace;overflow:auto';"
            "p.textContent='SESIONES ADK (GET /sessions)\\n\\n'+JSON.stringify(d,null,2);"
            "document.body.appendChild(p);return 'ok';})()",
            await_promise=True,
        )
        await asyncio.sleep(0.5)
        await shot("sessions.png")

    chrome.terminate()
    print("[capture] done")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=BASE)
    args = ap.parse_args()
    asyncio.run(main(args.base))
