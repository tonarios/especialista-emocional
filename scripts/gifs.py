"""Ensambla los frames de cada escenario en GIFs animados (Pillow, sin ffmpeg).

  outputs/gifs/frames/<escenario>/NNN.png  ->  outputs/gifs/<escenario>.gif

Se usa Pillow en vez de ffmpeg (el host no lo tiene y era el motivo por el que
M8 se cerró sin GIFs). La paleta se cuantiza con `Image.ADAPTIVE`, que para
capturas de UI da un resultado equivalente al `palettegen/paletteuse` de ffmpeg.

Uso: uv run python scripts/gifs.py [--width 900] [--ms 700]
"""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parent.parent
FRAMES = ROOT / "outputs" / "gifs" / "frames"
OUT = ROOT / "outputs" / "gifs"

# El último frame se sostiene más tiempo para que el bucle sea legible.
HOLD_LAST_MS = 2200

# Transiciones mínimas con cambio real para considerar que el GIF muestra algo.
MIN_CAMBIOS = 4


def build_gif(frames_dir: Path, width: int, ms: int, colors: int) -> Path | None:
    paths = sorted(frames_dir.glob("*.png"))
    if not paths:
        print(f"  [gifs] {frames_dir.name}: sin frames, se omite")
        return None

    rgb = []
    for p in paths:
        im = Image.open(p).convert("RGB")
        if im.width != width:
            h = round(im.height * width / im.width)
            im = im.resize((width, h), Image.LANCZOS)
        rgb.append(im)

    # Un GIF cuyos frames apenas cambian no es evidencia: suele significar que la
    # captura fotografió una pantalla estática (p. ej. una sesión restaurada) en
    # vez del recorrido. Mejor romper que publicar un GIF vacío.
    cambios = sum(
        1 for a, b in zip(rgb, rgb[1:]) if ImageChops.difference(a, b).getbbox()
    )
    if cambios < MIN_CAMBIOS:
        raise RuntimeError(
            f"{frames_dir.name}: solo {cambios} de {len(rgb) - 1} transiciones cambian "
            f"(mínimo {MIN_CAMBIOS}); la captura no recorrió el escenario"
        )

    # Paleta ÚNICA para todos los frames: si cada frame se cuantiza por separado,
    # los mismos píxeles reciben índices distintos y se pierde la compresión
    # delta entre frames (el GIF acaba pesando ~10x).
    # Se muestrean frames repartidos por todo el escenario y se montan en tira:
    # así entran también los colores que solo aparecen al final (p. ej. el rojo
    # de la burbuja de emergencia), que un muestreo del primer frame perdería.
    step = max(1, len(rgb) // 8)
    muestras = rgb[::step] + [rgb[-1]]
    tw, th = width // 3, rgb[0].height // 3
    tira = Image.new("RGB", (tw * len(muestras), th))
    for i, im in enumerate(muestras):
        tira.paste(im.resize((tw, th), Image.LANCZOS), (i * tw, 0))
    palette = tira.quantize(colors=colors, method=Image.MEDIANCUT, dither=Image.NONE)

    # Sin dithering: el fondo es un degradado y el ruido del dither dispara el
    # tamaño sin ganancia visible en una captura de UI.
    imgs = [im.quantize(palette=palette, dither=Image.NONE) for im in rgb]

    durations = [ms] * len(imgs)
    durations[-1] = HOLD_LAST_MS

    out = OUT / f"{frames_dir.name}.gif"
    imgs[0].save(
        out,
        save_all=True,
        append_images=imgs[1:],
        duration=durations,
        loop=0,
        optimize=True,
        # disposal=1 (no borrar) permite que Pillow escriba solo el rectángulo
        # que cambió entre frames; con disposal=2 cada frame va completo.
        disposal=1,
    )
    kb = out.stat().st_size / 1024
    print(f"  [gifs] {frames_dir.name}.gif — {len(imgs)} frames, {kb:.0f} KB")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--width", type=int, default=760, help="ancho de salida en px")
    ap.add_argument("--ms", type=int, default=700, help="ms por frame")
    ap.add_argument("--colors", type=int, default=128, help="colores de la paleta")
    args = ap.parse_args()

    if not FRAMES.is_dir() or not any(FRAMES.iterdir()):
        print(f"[gifs] no hay frames en {FRAMES}. Corre antes scripts/capture_evidence.py")
        return 1

    OUT.mkdir(parents=True, exist_ok=True)
    made = [build_gif(d, args.width, args.ms, args.colors)
            for d in sorted(FRAMES.iterdir()) if d.is_dir()]
    made = [m for m in made if m]
    print(f"[gifs] {len(made)} GIFs en {OUT}")
    return 0 if made else 1


if __name__ == "__main__":
    raise SystemExit(main())
