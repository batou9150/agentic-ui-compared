#!/usr/bin/env bash
# Record the side-by-side GIFs from the comparison UI (Scripted mode).
# Needs ffmpeg. Output: docs/media/<scenario>.gif
set -eo pipefail
cd "$(dirname "$0")/.."
rm -rf scenarios/test-results/record
(cd scenarios && npx playwright test -c record/playwright.config.ts)
mkdir -p docs/media
for video in scenarios/test-results/record/*/video.webm; do
  name=$(basename "$(dirname "$video")" | sed -E 's/^record-record-(S[0-9]).*/\1/')
  palette=$(mktemp -t palette).png
  filters="fps=6,scale=1100:-1:flags=lanczos"
  ffmpeg -loglevel error -y -i "$video" -vf "$filters,palettegen=max_colors=96" "$palette"
  ffmpeg -loglevel error -y -i "$video" -i "$palette" -lavfi "$filters [x]; [x][1:v] paletteuse=dither=bayer:bayer_scale=4" "docs/media/$name.gif"
  rm -f "$palette"
  echo "docs/media/$name.gif $(du -h "docs/media/$name.gif" | cut -f1)"
done
