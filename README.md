# Daily Paper Digest

Local CLI for sending a concise daily paper email digest focused on recommender systems, generative recommendation, LLM4Rec, and Agent4Rec.

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

Before applying the final limit, the CLI reranks a candidate pool with an LLM preference score. The scoring prompt prioritizes papers with online A/B or production traffic evidence, then top-conference publications, strong generative recommendation or semantic ID relevance, and author affiliations from well-known internet companies. Without an API key, the same preferences are approximated with deterministic metadata rules.

## Commands

```bash
python3 -m daily_paper fetch --out papers.json
python3 -m daily_paper preview --out preview.html
python3 -m daily_paper send --to recipient@example.com --dry-run
python3 -m daily_paper send --to recipient@example.com
python3 -m daily_paper site-data --out web/public/papers.json --limit 30
```

Use `paper_state.toml` to mark important papers. Important papers are placed first in the email.

## Sources

The digest searches arXiv first, then optionally queries DBLP for recommendation-related top conference papers from RecSys, SIGIR, WWW, KDD, WSDM, CIKM, ICLR, AAAI, ICML, and NeurIPS. DBLP is a supplemental source; if a DBLP venue query is unavailable or returns no matching records, the conference source automatically falls back to OpenAlex and Semantic Scholar, queries by venue/year plus recommendation keywords, then maps those results into the same `Paper` model.

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

Site data is updated incrementally. Each build searches the current window, selects the
current top papers, reuses existing DeepSeek analysis when the paper version and analysis
settings have not changed, and keeps older papers already present in `web/public/papers.json`.

Optional controls:

```bash
DAILY_PAPER_LIMIT=50 ./scripts/build_pages.sh
DAILY_PAPER_CONFIG=config.toml ./scripts/build_pages.sh
```

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
It runs every day at 08:00 Beijing time (`0 0 * * *` UTC), rebuilds the paper data and
the `docs/` site, then deploys the result to GitHub Pages.

Recommended GitHub deployment:

1. Create a GitHub repository and push this project.
2. In GitHub, open `Settings` -> `Secrets and variables` -> `Actions` and add:
   - `DEEPSEEK_API_KEY`: your DeepSeek API key. This is stored as a GitHub Actions secret and is not committed to the repository.
   - `SEMANTIC_SCHOLAR_API_KEY`: optional, improves Semantic Scholar fallback reliability.
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

To change the research domain, edit `config.toml`:

- `arxiv.categories`
- `arxiv.include_keywords`
- `arxiv.exclude_keywords`
- `dblp.venues`
- `dblp.include_keywords`

The website supports local importance marking in the browser. Marks are stored in `localStorage`; generated defaults still come from `paper_state.toml`.
