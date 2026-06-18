#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LIMIT="${DAILY_PAPER_LIMIT:-30}"
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
if ! command -v npm >/dev/null 2>&1; then
  echo "Error: npm is required to build the bundled GitHub Pages app without external CDN dependencies." >&2
  exit 1
fi
echo "Installing web dependencies..."
(cd web && npm ci)
echo "Building bundled web app..."
(cd web && npm run build)

echo "Done. Configure GitHub Pages to publish from: main / docs"
