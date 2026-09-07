"""Cliente mínimo de Chrome DevTools Protocol (sin Playwright).

Lo usan `capture_evidence.py` (escenarios + stills) y `report.py` (HTML→PDF).
Solo necesita Google Chrome instalado y `websockets`.
"""
from __future__ import annotations

import asyncio
import base64
import json
import subprocess
import time
import urllib.request
from contextlib import asynccontextmanager
from pathlib import Path

import websockets

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
DEBUG_PORT = 9222
USER_DATA_DIR = "/tmp/ah-emociones-chrome"


def launch_chrome(width: int = 900, height: int = 1000) -> subprocess.Popen:
    """Chrome headless con el puerto de depuración abierto."""
    return subprocess.Popen(
        [
            CHROME, "--headless=new", f"--remote-debugging-port={DEBUG_PORT}",
            f"--user-data-dir={USER_DATA_DIR}", "--no-first-run",
            "--disable-gpu", f"--window-size={width},{height}",
            "--hide-scrollbars", "about:blank",
        ],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def page_ws(retries: int = 20) -> str:
    for _ in range(retries):
        try:
            with urllib.request.urlopen(f"http://localhost:{DEBUG_PORT}/json") as r:
                for p in json.loads(r.read()):
                    if p.get("type") == "page":
                        return p["webSocketDebuggerUrl"]
        except Exception:
            time.sleep(0.5)
    raise RuntimeError("no se encontró un target page en CDP")


class Page:
    """Envoltura sobre el websocket de una pestaña."""

    def __init__(self, ws):
        self._ws = ws
        self._id = 0

    async def cmd(self, method: str, params: dict | None = None) -> dict:
        self._id += 1
        mid = self._id
        await self._ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(await self._ws.recv())
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})

    async def evaluate(self, expr: str, await_promise: bool = False):
        r = await self.cmd(
            "Runtime.evaluate",
            {"expression": expr, "returnByValue": True, "awaitPromise": await_promise},
        )
        return r.get("result", {}).get("value")

    async def navigate(self, url: str, settle: float = 2.5) -> None:
        await self.cmd("Page.navigate", {"url": url})
        await asyncio.sleep(settle)

    async def png(self) -> bytes:
        r = await self.cmd("Page.captureScreenshot", {"format": "png"})
        return base64.b64decode(r["data"])

    async def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(await self.png())


@asynccontextmanager
async def chrome_page(width: int = 900, height: int = 1000):
    """Arranca Chrome headless, entrega una `Page` y cierra al salir."""
    proc = launch_chrome(width, height)
    try:
        ws_url = page_ws()
        async with websockets.connect(ws_url, max_size=64 * 1024 * 1024) as ws:
            page = Page(ws)
            await page.cmd("Page.enable")
            await page.cmd("Runtime.enable")
            # El perfil de Chrome es persistente entre corridas: sin esto la
            # caché de disco sirve el frontend anterior y las capturas mienten.
            await page.cmd("Network.enable")
            await page.cmd("Network.setCacheDisabled", {"cacheDisabled": True})
            yield page
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
