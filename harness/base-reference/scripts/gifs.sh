#!/usr/bin/env bash
# Assemble PNG frames (captured with chrome-devtools) into animated GIFs with ffmpeg.
# Frames go in outputs/gifs/frames/<name>/NNN.png -> outputs/gifs/<name>.gif
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "ffmpeg not found."
  exit 1
fi

FRAMES_DIR="outputs/gifs/frames"
mkdir -p outputs/gifs

if [ ! -d "$FRAMES_DIR" ]; then
  echo "No frames at $FRAMES_DIR. Capture screenshots with chrome-devtools first." >&2
  exit 1
fi

for d in "$FRAMES_DIR"/*/; do
  [ -d "$d" ] || continue
  name="$(basename "$d")"
  echo "[gifs] $name -> outputs/gifs/$name.gif"
  if ls "$d"q*.png >/dev/null 2>&1; then
    ffmpeg -y -framerate 1 -i "$d/q%02d.png" \
      -vf "scale=1200:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse" \
      -loop 0 "outputs/gifs/$name.gif"
  else
    ffmpeg -y -framerate 1 -pattern_type glob -i "$d/*.png" \
      -vf "scale=1200:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse" \
      -loop 0 "outputs/gifs/$name.gif"
  fi
done
echo "[gifs] done."
