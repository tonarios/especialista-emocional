"""Captura la UI real (login + moon-chat) vía CDP y guarda frames para GIFs.

Flujo:
  1. navega a http://localhost:8000 -> captura pantalla de login
  2. rellena email/password y hace login real -> captura chat moon vacío
  3. envía una pregunta de álgebra -> captura frames mientras el tutor responde
Uso: uv run python harness/scripts/capture_ui.py <outdir>
"""
from __future__ import annotations

import asyncio
import base64
import json
import sys
import urllib.request
from pathlib import Path

import websockets


def _page_ws() -> str:
    with urllib.request.urlopen("http://localhost:9222/json") as r:
        pages = json.loads(r.read())
    for p in pages:
        if p.get("type") == "page":
            return p["webSocketDebuggerUrl"]
    raise RuntimeError("no page target found in CDP")


async def main(outdir: Path) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    async with websockets.connect(_page_ws(), max_size=50 * 1024 * 1024) as ws:
        _id = 0

        async def cmd(method: str, params: dict | None = None):
            nonlocal _id
            _id += 1
            await ws.send(json.dumps({"id": _id, "method": method, "params": params or {}}))
            while True:
                msg = json.loads(await ws.recv())
                if msg.get("id") == _id:
                    if "error" in msg:
                        raise RuntimeError(f"{method}: {msg['error']}")
                    return msg.get("result", {})

        async def evaluate(expr: str):
            r = await cmd("Runtime.evaluate", {"expression": expr, "returnByValue": True})
            return r.get("result", {}).get("value")

        async def shot(name: str):
            r = await cmd("Page.captureScreenshot", {"format": "png"})
            data = base64.b64decode(r["data"])
            (outdir / name).write_bytes(data)
            print(f"  [capture] {name} ({len(data)} bytes)")

        await cmd("Page.enable")
        await cmd("Runtime.enable")

        # 1. Login
        await cmd("Page.navigate", {"url": "http://localhost:8000/"})
        await asyncio.sleep(3)
        await shot("01_login.png")

        # 2. Rellenar credenciales y enviar (login real)
        await evaluate(
            "document.getElementById('auth-email').value='sofia@demo.com';"
            "document.getElementById('auth-password').value='clave123';"
        )
        await asyncio.sleep(1)
        await shot("02_credenciales.png")
        await evaluate("document.getElementById('auth-login').click()")
        await asyncio.sleep(3)
        # esperar a que el chat sea visible
        visible = await evaluate("!document.getElementById('chat-view').classList.contains('hidden')")
        print(f"  chat visible tras login: {visible}")
        await shot("03_chat_moon.png")

        # 3. Escribir pregunta y enviar
        await evaluate(
            "document.getElementById('input').value='Explícame qué son las ecuaciones lineales y ponme un ejercicio.';"
        )
        await asyncio.sleep(1)
        await shot("04_pregunta.png")
        await evaluate("document.getElementById('send').click()")

        # 4. Capturar mientras responde (espera el texto)
        for i in range(20):
            await asyncio.sleep(4)
            has_user = await evaluate("!!document.querySelector('.msg.user')")
            has_asst = await evaluate("!!document.querySelector('.msg.assistant')")
            done = await evaluate(
                "!document.querySelector('.msg.assistant .typing') && !!document.querySelector('.msg.assistant')"
            )
            if has_asst:
                await shot(f"05_respuesta_{i:02d}.png")
            print(f"  turno {i}: user={has_user} asst={has_asst} done={done}")
            if done:
                break
        await asyncio.sleep(2)
        await shot("06_final.png")
    print("[capture_ui] done")


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("outputs/gifs/frames/frontend")
    asyncio.run(main(out))
