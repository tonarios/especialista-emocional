"""Captura un escenario de usuario en la UI real (login + moon-chat) vía CDP.

Uso: uv run python harness/scripts/capture_scenario.py <email> <password> <prompt> <outdir>
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


async def main(email: str, password: str, prompt: str, outdir: Path) -> None:
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
            (outdir / name).write_bytes(base64.b64decode(r["data"]))
            print(f"  [capture] {name}")

        await cmd("Page.enable")
        await cmd("Runtime.enable")

        # Si ya hay sesión, cerrar para volver al login
        await evaluate("localStorage.removeItem('tutor_token'); localStorage.removeItem('tutor_email'); location.reload()")
        await asyncio.sleep(3)

        await cmd("Page.navigate", {"url": "http://localhost:8000/"})
        await asyncio.sleep(3)
        await shot("01_login.png")

        await evaluate(
            f"document.getElementById('auth-email').value={json.dumps(email)};"
            f"document.getElementById('auth-password').value={json.dumps(password)};"
        )
        await asyncio.sleep(1)
        await shot("02_credenciales.png")
        await evaluate("document.getElementById('auth-login').click()")
        await asyncio.sleep(3)
        visible = await evaluate("!document.getElementById('chat-view').classList.contains('hidden')")
        print(f"  chat visible tras login: {visible}")
        await shot("03_chat_moon.png")

        await evaluate(f"document.getElementById('input').value={json.dumps(prompt)};")
        await asyncio.sleep(1)
        await shot("04_pregunta.png")
        await evaluate("document.getElementById('send').click()")

        for i in range(25):
            await asyncio.sleep(4)
            has_asst = await evaluate("!!document.querySelector('.msg.assistant')")
            done = await evaluate(
                "!document.querySelector('.msg.assistant .typing') && !!document.querySelector('.msg.assistant')"
            )
            if has_asst:
                await shot(f"05_respuesta_{i:02d}.png")
            print(f"  turno {i}: asst={has_asst} done={done}")
            if done:
                break
        await asyncio.sleep(2)
        await shot("06_final.png")
    print("[capture_scenario] done")


if __name__ == "__main__":
    email, password, prompt = sys.argv[1], sys.argv[2], sys.argv[3]
    out = Path(sys.argv[4])
    asyncio.run(main(email, password, prompt, out))
