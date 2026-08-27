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
python3 -m daily_paper --config "$CONFIG" backfill --out web/public/papers.json --days 365 --per-topic 20

TRACK_ARGS=(--track llm_systems)
WEEKDAY="${DAILY_PAPER_WEEKDAY:-$(TZ=Asia/Shanghai date +%u)}"
if [ "$WEEKDAY" = "5" ]; then
  TRACK_ARGS+=(--track generative_rec)
  echo "Friday in Asia/Shanghai: including the weekly Generative Recommendation track."
fi

python3 -m daily_paper --config "$CONFIG" site-data \
  --out web/public/papers.json \
  --limit "$LIMIT" \
  "${TRACK_ARGS[@]}"

if [ "${DAILY_PAPER_SEND:-false}" = "true" ]; then
  echo "Sending the daily LLM systems digest..."
  if ! python3 -m daily_paper --config "$CONFIG" send \
      --track llm_systems \
      --data web/public/papers.json \
      --to "${DAILY_PAPER_TO:-}"; then
    echo "Warning: LLM systems email failed; continuing with other tracks and site deployment." >&2
  fi
  if [ "$WEEKDAY" = "5" ]; then
    echo "Sending the Friday Generative Recommendation digest..."
    if ! python3 -m daily_paper --config "$CONFIG" send \
        --track generative_rec \
        --data web/public/papers.json \
        --to "${DAILY_PAPER_TO:-}"; then
      echo "Warning: Generative Recommendation email failed; continuing with site deployment." >&2
    fi
  fi
else
  echo "Email delivery disabled (DAILY_PAPER_SEND is not true)."
fi

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
