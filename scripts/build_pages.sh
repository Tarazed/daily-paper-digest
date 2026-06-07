#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LIMIT="${DAILY_PAPER_LIMIT:-10}"
CONFIG="${DAILY_PAPER_CONFIG:-config.toml}"

cd "$ROOT_DIR"

set -a
if [ -f ".env" ]; then
  # shellcheck disable=SC1091
  . ./.env
fi
if [ -f ".env.local" ]; then
  # shellcheck disable=SC1091
  . ./.env.local
fi
set +a

if [ -z "${DEEPSEEK_API_KEY:-}" ]; then
  echo "Warning: DEEPSEEK_API_KEY is not set. Site analysis will use fallback text."
fi

echo "Generating site data..."
python3 -m daily_paper --config "$CONFIG" site-data --out web/public/papers.json --limit "$LIMIT"

echo "Building GitHub Pages site into docs/..."
python3 scripts/build_static_site.py

echo "Done. Configure GitHub Pages to publish from: main / docs"
