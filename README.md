# Daily Paper Digest

Local CLI and GitHub Pages dashboard for two isolated research tracks:

- `llm_systems`: daily LLM RL, post-training, and agent research (12 papers: 4/4/4 with unused places redistributed).
- `generative_rec`: a Friday Generative Recommendation digest (10 papers).

Both tracks share acquisition and metadata infrastructure, but membership, scoring, quotas, email sections, and web views remain separate.

## Setup

Do not commit passwords, API keys, email authorization codes, or personal email settings.
Use local environment variables or `.env.local` instead. The `.env.local` file is ignored by git.

Create local config:

```bash
cp .env.example .env.local
```

Then edit `.env.local` on your machine only.

Set SMTP credentials before real sending:

```bash
export SMTP_HOST=smtp.qq.com
export SMTP_PORT=465
export SMTP_SSL=true
export SMTP_USER='<your email address>'
export SMTP_PASSWORD='<QQ Mail authorization code>'
```

Optional DeepSeek summaries and affiliation cleanup:

```bash
export DEEPSEEK_API_KEY='<your key>'
```

Without `DEEPSEEK_API_KEY`, the CLI still runs and falls back to a shortened abstract summary.

The default model is `deepseek-v4-flash` at `https://api.deepseek.com`, using DeepSeek's OpenAI-compatible Chat Completions API. The CLI also enriches missing affiliations from multiple sources when available: OpenAlex, Crossref, Semantic Scholar, and arXiv source files. Multi-source matches are preferred, with high-confidence single-source results used as a fallback when other sources do not expose affiliation data.

Before applying quotas, each paper is classified and scored within its own track. Public membership requires relevance `>= 70`. LLM-system papers are scored on relevance, technical contribution, evidence, novelty, and reproducibility. GR keeps its existing preference score, including production and online A/B evidence. Without an API key, deterministic rules provide a conservative fallback.

## Commands

```bash
# One-time, idempotent cold start: preceding 365 days, up to 20 classics/topic.
python3 -m daily_paper backfill --out web/public/papers.json --days 365 --per-topic 20

# Track-aware site updates.
python3 -m daily_paper site-data --out web/public/papers.json --track llm_systems
python3 -m daily_paper site-data --out web/public/papers.json --track generative_rec

# Preview and send a single isolated track.
python3 -m daily_paper preview --track llm_systems --data web/public/papers.json --out preview.html
python3 -m daily_paper send --track llm_systems --data web/public/papers.json --to recipient@example.com --dry-run
python3 -m daily_paper send --track generative_rec --data web/public/papers.json --to recipient@example.com
```

Use `paper_state.toml` to mark important papers. Important papers are placed first in the email.

Delivery progress lives in `digest_state.json`. It records successful timestamps, sent IDs, cold-start completion, and the classic-review cursor. The first 20 successful LLM daily emails append three unique classics without reducing the 12 new-paper quota. Dry runs and failed SMTP calls do not advance state. To intentionally rebuild the cold start, back up the file, clear `cold_start_completed_at`, `foundation_review_ids`, and `foundation_review_cursor`, then run `backfill` again.

## Sources

The digest searches arXiv and conference metadata independently for each track. LLM sources cover the configured NLP/ML/agent venues and explicitly exclude traditional robotics or control RL without material language-model context. GR retains its recommendation-focused venues. If a DBLP venue query is unavailable or empty, the source falls back to OpenAlex and Semantic Scholar and maps results into the same canonical `Paper` model.

DBLP venue queries, fallback conference queries, and LLM summary/analysis calls are parallelized. Tune `dblp.workers`, `dblp.fallback_workers`, `summary.summary_workers`, and `summary.analysis_workers` in `config.toml` to balance speed against API rate limits. Semantic Scholar works without a key for light use, but setting `SEMANTIC_SCHOLAR_API_KEY` locally or as a GitHub Actions secret is recommended.

## GitHub Pages Website

The website is a React single-page dashboard. It reads `web/public/papers.json` and builds static files into `docs/`, which GitHub Pages can publish directly.

One-command local build:

```bash
./scripts/build_pages.sh
```

`build_pages.sh` loads `.env` and `.env.local` automatically. Put `DEEPSEEK_API_KEY`
in `.env.local` for local builds. Without `DEEPSEEK_API_KEY`, the site still builds
with fallback summaries.

Site data is updated incrementally. Each build refreshes the daily LLM track; Friday builds
also refresh GR. Existing analysis is reused when the paper version and analysis settings
have not changed, while the canonical archive and browser-local marks remain compatible.

Optional controls:

```bash
DAILY_PAPER_LIMIT=50 ./scripts/build_pages.sh
DAILY_PAPER_CONFIG=config.toml ./scripts/build_pages.sh
DAILY_PAPER_WEEKDAY=5 ./scripts/build_pages.sh  # exercise Friday behavior locally
DAILY_PAPER_SEND=true DAILY_PAPER_TO=reader@example.com ./scripts/build_pages.sh
```

`DAILY_PAPER_SEND` defaults to false. A normal local build or repository push therefore never sends email. The build and cold start also work without LLM API keys; summaries and scoring use deterministic fallback behavior.

Local development preview:

```bash
./scripts/preview_pages.sh
```

Then open `http://127.0.0.1:5173`.

GitHub Pages setup for manual publishing from `docs/`:

1. Push this repository to GitHub.
2. Run `./scripts/build_pages.sh` locally and commit the generated `docs/` directory.
3. In GitHub repository settings, set Pages source to `main` branch and `/docs` folder.

## Daily 08:00 Beijing Time Updates

The repository includes a GitHub Actions workflow at `.github/workflows/daily-pages.yml`.
It runs every day at 08:00 Beijing time (`0 0 * * *` UTC), rebuilds the LLM track and
the `docs/` site, adds GR on Friday in `Asia/Shanghai`, persists both paper JSON files plus
`digest_state.json`, and deploys to GitHub Pages. Push events build/deploy but never send.
Scheduled runs send when SMTP secrets are configured; manual runs send only when the
`send_email` input is explicitly enabled.

Recommended GitHub deployment:

1. Create a GitHub repository and push this project.
2. In GitHub, open `Settings` -> `Secrets and variables` -> `Actions` and add:
   - `DEEPSEEK_API_KEY`: your DeepSeek API key. This is stored as a GitHub Actions secret and is not committed to the repository.
   - `SEMANTIC_SCHOLAR_API_KEY`: optional, improves Semantic Scholar fallback reliability.
   - `DAILY_PAPER_TO`, `SMTP_USER`, and `SMTP_PASSWORD`: required for scheduled email delivery. The checked-in workflow uses the mailer's default QQ SMTP settings; customize the workflow env if another provider is needed.
3. Open `Settings` -> `Pages` and set:
   - Source: `GitHub Actions`
4. Open `Actions` -> `Daily Paper Pages` and click `Run workflow` once to test it.

If you do not want to store any secret on GitHub, do not add `DEEPSEEK_API_KEY`.
The scheduled workflow will still run, but generated analysis fields use fallback text.

Local scheduled updates are also possible. On macOS/Linux, add a cron entry:

```cron
0 8 * * * cd "/path/to/daily paper" && /bin/bash ./scripts/build_pages.sh && git add docs web/public/papers.json && (git diff --cached --quiet || (git commit -m "Update daily paper site" && git push))
```

Use GitHub Actions unless you need the update to depend on local-only network access or files.

To change either research domain, edit its profile in `config.toml`:

- `tracks.<track>.arxiv.categories`
- `tracks.<track>.arxiv.include_keywords`
- `tracks.<track>.arxiv.exclude_keywords`
- `tracks.<track>.dblp.venues`
- `tracks.<track>.dblp.include_keywords`

The website supports local importance marking in the browser. Marks are stored in `localStorage`; generated defaults still come from `paper_state.toml`.
