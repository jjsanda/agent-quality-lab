#!/usr/bin/env bash
# Render every Mermaid .mmd under docs/diagrams to SVG + PNG via @mermaid-js/mermaid-cli.
# Uses `mmdc` if on PATH, otherwise `npx`. Requires Node.js.
set -euo pipefail

DIR="docs/diagrams"
OUT="$DIR/rendered"
CONFIG="$DIR/puppeteer-config.json"
mkdir -p "$OUT"

if command -v mmdc >/dev/null 2>&1; then
    MMDC=(mmdc)
else
    MMDC=(npx -y -p @mermaid-js/mermaid-cli mmdc)
fi

shopt -s nullglob
sources=("$DIR"/*.mmd)
if [ ${#sources[@]} -eq 0 ]; then
    echo "no .mmd files in $DIR" >&2
    exit 1
fi

for src in "${sources[@]}"; do
    name="$(basename "$src" .mmd)"
    for fmt in svg png; do
        "${MMDC[@]}" -i "$src" -o "$OUT/$name.$fmt" -b white -t default -p "$CONFIG" -s 2
    done
    echo "rendered $name (svg, png)"
done
