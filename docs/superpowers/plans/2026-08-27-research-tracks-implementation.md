# Research Tracks and Cold Start Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert Daily Paper Digest from one GR-focused stream into isolated daily LLM-systems and weekly GR tracks, including a 365-day cold start and a 60-paper foundations collection.

**Architecture:** Keep one canonical `Paper` record and shared acquisition/analysis infrastructure. Add track profiles, track-aware classification/scoring/selection, durable delivery state, and track-aware site/email views. Implement the cold start as an idempotent extension of the same pipeline rather than a second data store.

**Tech Stack:** Python 3.11 standard library and pytest; React 17, esbuild, Node test runner; GitHub Actions and GitHub Pages.

## Global Constraints

- `llm_systems` is the default track; `generative_rec` remains the secondary track.
- Public track membership requires relevance score `>= 70`.
- Daily LLM quota is 12 using `post_training=4`, `llm_rl=4`, and `llm_agent=4`, with unused places redistributed.
- GR quota is 10 and its scheduled day is Friday at 08:00 Asia/Shanghai.
- Cold start covers the preceding 365 calendar days and selects up to 20 foundations per LLM topic.
- The first 20 successful daily sends append three unique foundation reviews without reducing the 12-paper daily quota.
- Existing paper IDs, GR history, cached analysis, state-file values, and browser-local marks remain compatible.
- Traditional robotics/control RL without material language-model context is excluded.
- No new runtime dependency is required.

## File Structure

- `daily_paper/config.py`: track profile dataclasses and backward-compatible TOML parsing.
- `daily_paper/models.py`: canonical paper fields for tracks, scores, foundations, citation metadata, and research details.
- `daily_paper/tracks.py`: deterministic topic classification, relevance gate, scoring normalization, and quota selection.
- `daily_paper/pipeline.py`: per-track acquisition, global deduplication, classification/scoring orchestration, and history merge.
- `daily_paper/foundations.py`: age-normalized foundation scoring, diversity constraints, and classic batches.
- `daily_paper/digest_state.py`: atomic durable state for successful runs, sent IDs, cold-start completion, and review progress.
- `daily_paper/summarizer.py`: LLM track classification/scoring and track-aware analysis prompts with deterministic fallback.
- `daily_paper/cli.py`: track-aware fetch/site/preview/send commands and the `backfill` command.
- `daily_paper/email_template.py`: separate primary, GR, and classic-review email sections.
- `daily_paper/conference_sources.py`: citation-count ingestion and merge.
- `web/src/paper-utils.mjs`: testable track/view/filter utilities.
- `web/src/main.jsx`, `web/src/styles.css`: track tabs, topic tabs, foundations view, and track-specific cards.
- `web/scripts/build.mjs`: preserve `docs/superpowers` while replacing generated Pages artifacts.
- `.github/workflows/daily-pages.yml`: daily site/LLM build and Friday GR selection with durable generated state.
- `config.toml`, `README.md`: production track profiles and operating documentation.

---

### Task 1: Preserve source documentation and add track configuration

**Files:**
- Modify: `web/scripts/build.mjs`
- Modify: `daily_paper/config.py`
- Modify: `config.toml`
- Modify: `tests/test_state_config.py`

**Interfaces:**
- Produces: `TrackConfig(key, label, enabled, cadence, weekly_day, quota, relevance_threshold, topic_quotas, arxiv, dblp)`.
- Produces: `AppConfig.tracks: Dict[str, TrackConfig]`, `AppConfig.default_track`, and `AppConfig.digest_state_file`.
- Preserves: `AppConfig.arxiv` and `AppConfig.dblp` as aliases for the GR profile during migration.

- [ ] **Step 1: Write failing config and build-preservation tests**

```python
def test_load_config_builds_explicit_track_profiles(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('''
default_track = "llm_systems"
digest_state_file = "digest_state.json"
[tracks.llm_systems]
label = "RL · Post-training · Agent"
cadence = "daily"
quota = 12
relevance_threshold = 70
[tracks.llm_systems.topic_quotas]
post_training = 4
llm_rl = 4
llm_agent = 4
[tracks.llm_systems.arxiv]
categories = ["cs.CL", "cs.AI"]
include_keywords = ["RLHF", "tool use"]
exclude_keywords = ["robot control"]
max_results = 120
days_back = 7
''', encoding="utf-8")
    config = load_config(str(path))
    track = config.tracks["llm_systems"]
    assert config.default_track == "llm_systems"
    assert track.topic_quotas == {"post_training": 4, "llm_rl": 4, "llm_agent": 4}
    assert track.arxiv.categories == ["cs.CL", "cs.AI"]
```

Add `web/tests/build-preservation.test.mjs`:

```javascript
import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

test("build script does not recursively delete docs", () => {
  const source = fs.readFileSync(new URL("../scripts/build.mjs", import.meta.url), "utf8");
  assert.equal(source.includes("fs.rmSync(docsDir, { recursive: true"), false);
  assert.equal(source.includes("generatedPaths"), true);
});
```

- [ ] **Step 2: Run the focused tests and verify failure**

Run: `pytest tests/test_state_config.py::test_load_config_builds_explicit_track_profiles -v && node --test web/tests/build-preservation.test.mjs`

Expected: Python fails because `AppConfig.tracks` is missing; Node fails because the build script deletes `docs` recursively.

- [ ] **Step 3: Implement track config parsing and targeted Pages cleanup**

```python
@dataclass
class TrackConfig:
    key: str
    label: str
    enabled: bool
    cadence: str
    weekly_day: str
    quota: int
    relevance_threshold: int
    topic_quotas: Dict[str, int]
    arxiv: ArxivConfig
    dblp: DblpConfig
```

Parse nested `tracks.<key>.arxiv`, `tracks.<key>.dblp`, and `tracks.<key>.topic_quotas` with helpers `_parse_arxiv_config` and `_parse_dblp_config`. When no `[tracks]` section exists, synthesize `generative_rec` from legacy `[arxiv]` and `[dblp]` values.

Replace the recursive docs deletion in `web/scripts/build.mjs` with:

```javascript
const generatedPaths = [assetsDir, path.join(docsDir, "index.html"), path.join(docsDir, "papers.json"), path.join(docsDir, ".nojekyll")];
for (const generatedPath of generatedPaths) {
  fs.rmSync(generatedPath, { recursive: true, force: true });
}
fs.mkdirSync(assetsDir, { recursive: true });
```

- [ ] **Step 4: Add both production profiles to `config.toml`**

Define `llm_systems` with the three confirmed topic families, `cs.CL/cs.AI/cs.LG/cs.MA`, the confirmed venues, daily quota 12, and hard exclusions for robotics/control-only work. Move the current GR source rules under `tracks.generative_rec`; keep the legacy sections until Task 10 removes their authority.

- [ ] **Step 5: Run tests and commit**

Run: `pytest tests/test_state_config.py -v && node --test web/tests/build-preservation.test.mjs`

Expected: all focused tests pass.

```bash
git add daily_paper/config.py config.toml tests/test_state_config.py web/scripts/build.mjs web/tests/build-preservation.test.mjs
git commit -m "feat: add research track configuration"
```

### Task 2: Extend the canonical paper model and legacy migration

**Files:**
- Modify: `daily_paper/models.py`
- Modify: `daily_paper/cli.py`
- Modify: `daily_paper/conference_sources.py`
- Modify: `tests/test_site_incremental.py`
- Modify: `tests/test_dblp.py`

**Interfaces:**
- Produces fields: `tracks`, `primary_track`, `topics`, `primary_topic`, `track_relevance`, `track_relevance_evidence`, `track_scores`, `track_score_rationales`, `track_score_breakdowns`, `foundation`, `foundation_score`, `citation_count`, and `research_details`.
- Produces: `_paper_from_dict(values, legacy_track="generative_rec") -> Paper`.

- [ ] **Step 1: Write failing legacy and citation tests**

```python
def test_load_previous_site_papers_migrates_legacy_record_to_gr(tmp_path):
    path = tmp_path / "papers.json"
    path.write_text(json.dumps({"papers": [asdict(make_paper("arxiv:legacy"))]}), encoding="utf-8")
    loaded = _load_previous_site_papers(str(path))
    assert loaded[0].tracks == ["generative_rec"]
    assert loaded[0].primary_track == "generative_rec"

def test_openalex_mapping_keeps_citation_count():
    paper = _openalex_work_to_paper(OPENALEX_WORK_WITH_CITATIONS, DblpVenueConfig("ICLR", "ICLR"))
    assert paper.citation_count == 42
```

- [ ] **Step 2: Verify the tests fail**

Run: `pytest tests/test_site_incremental.py::test_load_previous_site_papers_migrates_legacy_record_to_gr tests/test_dblp.py::test_openalex_mapping_keeps_citation_count -v`

Expected: failures for missing model fields.

- [ ] **Step 3: Add model fields and migration defaults**

```python
tracks: List[str] = field(default_factory=list)
primary_track: str = ""
topics: List[str] = field(default_factory=list)
primary_topic: str = ""
track_relevance: Dict[str, int] = field(default_factory=dict)
track_relevance_evidence: Dict[str, str] = field(default_factory=dict)
track_scores: Dict[str, int] = field(default_factory=dict)
track_score_rationales: Dict[str, str] = field(default_factory=dict)
track_score_breakdowns: Dict[str, Dict[str, int]] = field(default_factory=dict)
foundation: bool = False
foundation_score: int = 0
citation_count: int = 0
research_details: Dict[str, object] = field(default_factory=dict)
```

In `_paper_from_dict`, copy these values when present. If `tracks` is absent or empty on a legacy site record, set `tracks=[legacy_track]` and `primary_track=legacy_track`.

- [ ] **Step 4: Map and merge OpenAlex/Semantic Scholar citation counts**

Read `cited_by_count` from OpenAlex and `citationCount` from Semantic Scholar, add `citationCount` to `_semantic_scholar_fields`, and merge with `target.citation_count = max(target.citation_count, source.citation_count)`.

- [ ] **Step 5: Run tests and commit**

Run: `pytest tests/test_site_incremental.py tests/test_dblp.py -v`

Expected: all tests pass.

```bash
git add daily_paper/models.py daily_paper/cli.py daily_paper/conference_sources.py tests/test_site_incremental.py tests/test_dblp.py
git commit -m "feat: add track metadata to papers"
```

### Task 3: Implement deterministic track classification and the relevance gate

**Files:**
- Create: `daily_paper/tracks.py`
- Create: `tests/test_tracks.py`

**Interfaces:**
- Produces: `TrackMatch(track: str, relevance: int, topics: List[str], primary_topic: str, evidence: str)`.
- Produces: `classify_deterministically(paper: Paper, track: TrackConfig) -> TrackMatch`.
- Produces: `apply_track_match(paper: Paper, match: TrackMatch, threshold: int) -> bool`.

- [ ] **Step 1: Write failing classification tests**

```python
def test_grpo_reasoning_paper_is_llm_rl():
    paper = make_paper("GRPO for Reinforcement Learning of Language Model Reasoning", "We train a large language model with verifiable rewards.")
    match = classify_deterministically(paper, llm_track())
    assert match.primary_topic == "llm_rl"
    assert match.relevance >= 70

def test_tool_memory_paper_is_llm_agent():
    paper = make_paper("Long-Horizon Tool Agents with Episodic Memory", "Language-model agents plan and call tools.")
    match = classify_deterministically(paper, llm_track())
    assert match.topics == ["llm_agent"]

def test_robot_control_without_llm_context_is_rejected():
    paper = make_paper("Offline Reinforcement Learning for Robot Control", "A policy learns locomotion from demonstrations.")
    assert classify_deterministically(paper, llm_track()).relevance < 70
```

- [ ] **Step 2: Run tests and verify failure**

Run: `pytest tests/test_tracks.py -v`

Expected: import failure because `daily_paper.tracks` does not exist.

- [ ] **Step 3: Implement topic rules and classification**

```python
TOPIC_TERMS = {
    "post_training": ("supervised fine tuning", "sft", "direct preference optimization", "dpo", "reward model", "process reward", "distillation", "self improvement"),
    "llm_rl": ("rlhf", "rlaif", "ppo", "grpo", "reinforcement learning for reasoning", "verifiable reward", "credit assignment", "reward hacking"),
    "llm_agent": ("language model agent", "llm agent", "tool use", "function calling", "agent memory", "multi agent", "computer use", "agent evaluation"),
}
LLM_CONTEXT = ("language model", "llm", "foundation model", "reasoning model", "transformer")
HARD_EXCLUDES = ("robot control", "robotic manipulation", "locomotion", "autonomous driving", "power grid control")
```

Normalize punctuation before matching. Assign all matching topics, choose the primary topic by contribution-specific term count with tie order `llm_rl`, `post_training`, `llm_agent`, and return 70 plus up to 25 evidence points. Require explicit LLM context and reject any hard exclusion unless the text also contains an explicit `llm agent` or `language model agent` phrase.

- [ ] **Step 4: Implement membership application**

`apply_track_match` stores relevance and evidence, adds the track only when the configured threshold is met, merges topics without duplicates, and sets primary fields only when this is the paper's first accepted track or the match has higher relevance.

- [ ] **Step 5: Run tests and commit**

Run: `pytest tests/test_tracks.py -v`

Expected: all classification tests pass.

```bash
git add daily_paper/tracks.py tests/test_tracks.py
git commit -m "feat: classify LLM research tracks"
```

### Task 4: Add track-specific scores and quota selection

**Files:**
- Modify: `daily_paper/tracks.py`
- Modify: `tests/test_tracks.py`

**Interfaces:**
- Produces: `apply_track_score(paper, track_key, breakdown, rationale) -> int`.
- Produces: `select_track_digest(papers, track_key, quota, topic_quotas, sent_ids=()) -> List[Paper]`.

- [ ] **Step 1: Write failing score and allocation tests**

```python
def test_llm_score_uses_confirmed_100_point_dimensions():
    paper = make_paper("A", "language model")
    score = apply_track_score(paper, "llm_systems", {"relevance": 30, "technical": 22, "evidence": 18, "novelty": 12, "reproducibility": 7}, "strong")
    assert score == 89
    assert paper.track_scores["llm_systems"] == 89

def test_selector_reserves_topics_and_redistributes_empty_quota():
    papers = scored_papers(post_training=5, llm_rl=5, llm_agent=1)
    selected = select_track_digest(papers, "llm_systems", 9, {"post_training": 3, "llm_rl": 3, "llm_agent": 3})
    assert len(selected) == 9
    assert sum(p.primary_topic == "llm_agent" for p in selected) == 1
    assert len({p.id for p in selected}) == 9
```

- [ ] **Step 2: Verify failure**

Run: `pytest tests/test_tracks.py -v`

Expected: missing scoring/selection functions.

- [ ] **Step 3: Implement score validation**

```python
LLM_SCORE_LIMITS = {"relevance": 30, "technical": 25, "evidence": 20, "novelty": 15, "reproducibility": 10}

def apply_track_score(paper, track_key, breakdown, rationale):
    cleaned = {key: max(0, min(LLM_SCORE_LIMITS[key], int(breakdown.get(key, 0)))) for key in LLM_SCORE_LIMITS}
    score = sum(cleaned.values())
    paper.track_score_breakdowns[track_key] = cleaned
    paper.track_scores[track_key] = score
    paper.track_score_rationales[track_key] = str(rationale).strip()
    return score
```

Use the existing GR score as the `generative_rec` fallback, stored independently in `track_scores`.

- [ ] **Step 4: Implement stable quota selection**

Sort by `(-track_score, -published_timestamp, title)`, fill each primary-topic reservation, then fill unused positions from the remaining global order. Exclude `sent_ids`, papers below the public relevance threshold, and duplicate paper IDs.

- [ ] **Step 5: Run tests and commit**

Run: `pytest tests/test_tracks.py tests/test_filtering.py -v`

Expected: all tests pass, including unchanged GR tests.

```bash
git add daily_paper/tracks.py tests/test_tracks.py
git commit -m "feat: rank and allocate track digests"
```

### Task 5: Add LLM-assisted track analysis with deterministic fallback

**Files:**
- Modify: `daily_paper/summarizer.py`
- Modify: `tests/test_summarizer.py`

**Interfaces:**
- Produces: `classify_and_score_track(papers, track, summary_config) -> List[Paper]`.
- Produces: `ChatCompletionClient.classify_and_score_track(paper, track_key, language="zh") -> Dict[str, object]`.
- Updates: `research_details` with the confirmed training/agent fields.

- [ ] **Step 1: Write failing payload and fallback tests**

```python
def test_track_scoring_prompt_uses_llm_dimensions(monkeypatch):
    captured = install_fake_chat(monkeypatch, {"relevance": 29, "technical": 24, "evidence": 18, "novelty": 14, "reproducibility": 9, "topics": ["llm_rl"], "primary_topic": "llm_rl", "evidence_text": "GRPO reasoning", "research_details": {"feedback_source": "verifiable rewards"}})
    client = ChatCompletionClient("key", "https://example.test", "model")
    result = client.classify_and_score_track(make_paper(), "llm_systems")
    prompt = captured["payload"]["messages"][0]["content"]
    assert "relevance 0-30" in prompt
    assert result["primary_topic"] == "llm_rl"

def test_track_scoring_without_key_uses_deterministic_gate(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    paper = make_paper(title="GRPO for language model reasoning")
    classify_and_score_track([paper], llm_track(), make_summary_config())
    assert paper.track_relevance["llm_systems"] >= 70
    assert paper.track_scores["llm_systems"] > 0
```

- [ ] **Step 2: Verify failure**

Run: `pytest tests/test_summarizer.py -v`

Expected: missing track analysis methods.

- [ ] **Step 3: Implement the strict JSON prompt and application**

Require `topics`, `primary_topic`, `relevance`, five confirmed score dimensions, `evidence_text`, `rationale`, and `research_details`. Clamp all numeric values through `apply_track_score`; discard unknown topics; apply the 70-point membership gate. On HTTP/JSON failure, call `classify_deterministically` and a conservative dimension fallback.

- [ ] **Step 4: Extend site analysis for research details**

For `llm_systems`, request these keys without guessing: `training_objective`, `feedback_source`, `model_data_scale`, `key_benchmarks`, `artifacts`, `agent_environment`, `agent_mechanism`, `interaction_horizon`, and `agent_evaluation`. Keep GR's A/B instructions only for papers in `generative_rec`.

- [ ] **Step 5: Run tests and commit**

Run: `pytest tests/test_summarizer.py tests/test_filtering.py -v`

Expected: all tests pass.

```bash
git add daily_paper/summarizer.py tests/test_summarizer.py
git commit -m "feat: analyze papers by research track"
```

### Task 6: Build the multi-track pipeline and track-aware site payload

**Files:**
- Create: `daily_paper/pipeline.py`
- Modify: `daily_paper/cli.py`
- Modify: `tests/test_site_incremental.py`
- Create: `tests/test_pipeline.py`

**Interfaces:**
- Produces: `fetch_track_candidates(track, fetch_arxiv=fetch_papers, fetch_conferences=fetch_dblp_papers) -> List[Paper]`.
- Produces: `build_track(track_key, config, previous_papers, state, limit=None, days_back=None, fetch_arxiv=fetch_papers, fetch_conferences=fetch_dblp_papers) -> TrackBuildResult`.
- Produces payload keys: `default_track`, `tracks`, `topics`, `foundations`, and canonical `papers`.

- [ ] **Step 1: Write failing pipeline-isolation tests**

```python
def test_build_track_keeps_scores_isolated(monkeypatch):
    paper = make_paper("arxiv:cross", "LLM Agent for Generative Recommendation")
    result = build_track("llm_systems", config(), [], {}, fetch_arxiv=lambda _: [paper], fetch_conferences=lambda _: [])
    assert "llm_systems" in result.papers[0].tracks
    assert "generative_rec" not in result.papers[0].track_scores

def test_site_payload_keeps_one_cross_track_record(tmp_path, monkeypatch):
    payload = build_site_payload(two_track_results_with_same_paper(), previous_papers=[], config=config())
    assert [p["id"] for p in payload["papers"]] == ["arxiv:cross"]
    assert payload["default_track"] == "llm_systems"
```

- [ ] **Step 2: Verify failure**

Run: `pytest tests/test_pipeline.py tests/test_site_incremental.py -v`

Expected: missing pipeline module and payload builder.

- [ ] **Step 3: Implement per-track fetch isolation**

Catch arXiv and conference errors independently, return available results, and raise only when both sources fail and no cached track history exists. Deduplicate by arXiv ID, DOI, then normalized title/year. Apply state values once after global deduplication.

- [ ] **Step 4: Implement canonical cross-track merge**

Merge memberships, topics, relevance maps, score maps, research details, and the strongest shared metadata into one paper. Preserve existing cached analysis when signatures match. Sort the canonical archive by publication time while each track exposes its own ordered paper-ID list.

- [ ] **Step 5: Update CLI site-data path**

`site-data` builds the daily `llm_systems` track on every run and builds GR only on Friday or with `--track generative_rec`. Serialize track metadata separately from canonical papers. Keep `_load_previous_site_papers` compatible with old payloads.

- [ ] **Step 6: Run tests and commit**

Run: `pytest tests/test_pipeline.py tests/test_site_incremental.py -v`

Expected: all tests pass.

```bash
git add daily_paper/pipeline.py daily_paper/cli.py tests/test_pipeline.py tests/test_site_incremental.py
git commit -m "feat: build isolated research tracks"
```

### Task 7: Implement durable digest state and foundations cold start

**Files:**
- Create: `daily_paper/digest_state.py`
- Create: `daily_paper/foundations.py`
- Create: `tests/test_digest_state.py`
- Create: `tests/test_foundations.py`
- Modify: `daily_paper/cli.py`

**Interfaces:**
- Produces: `DigestState(last_success, sent_ids, cold_start_completed_at, foundation_review_ids, foundation_review_cursor)`.
- Produces: `load_digest_state(path)`, `save_digest_state(path, state)` with atomic replacement.
- Produces: `foundation_score(paper, now) -> int`, `select_foundations(papers, per_topic=20, now=None)`, and `next_foundation_batch(papers, state, count=3)`.

- [ ] **Step 1: Write failing state and foundation tests**

```python
def test_digest_state_round_trip_is_atomic(tmp_path):
    path = tmp_path / "digest_state.json"
    state = DigestState(sent_ids={"llm_systems": ["arxiv:1"]}, foundation_review_cursor=3)
    save_digest_state(str(path), state)
    assert load_digest_state(str(path)) == state
    assert not (tmp_path / "digest_state.json.tmp").exists()

def test_foundation_score_normalizes_citations_by_age():
    old = paper_with_citations("old", citations=100, published="2025-09-01")
    new = paper_with_citations("new", citations=50, published="2026-07-01")
    assert citation_velocity_points(new, date(2026, 8, 27)) > citation_velocity_points(old, date(2026, 8, 27))

def test_next_batch_never_repeats_foundation():
    state = DigestState(foundation_review_ids=["p1", "p2", "p3", "p4"], foundation_review_cursor=0)
    first = next_foundation_batch(make_foundations(4), state, 3)
    second = next_foundation_batch(make_foundations(4), state, 3)
    assert [p.id for p in first] == ["p1", "p2", "p3"]
    assert [p.id for p in second] == ["p4"]
```

- [ ] **Step 2: Verify failure**

Run: `pytest tests/test_digest_state.py tests/test_foundations.py -v`

Expected: module import failures.

- [ ] **Step 3: Implement atomic state and successful-send advancement**

Write JSON to `<path>.tmp`, flush and `os.fsync`, then `os.replace`. Keep state unchanged for dry runs and failed sends. Store sent IDs per track and ISO timestamps for last successful runs.

- [ ] **Step 4: Implement the 100-point foundation formula**

Use caps `25/25/15/15/10/10` for relevance, foundational contribution, evidence, age-normalized citation velocity, reproducibility, and venue recognition. Citation velocity is `citation_count / max(age_days / 30.0, 1.0)` and maps to 0–15 with thresholds `[0, 1, 2, 4, 8, 16]`.

- [ ] **Step 5: Implement diversity selection**

For each primary topic, greedily select by foundation score while enforcing at most four matching normalized model/method-series labels, three recurring author-group keys, and six papers per publication month. If fewer than 20 are selected, relax month, author, then series constraints in that order and record relaxations.

- [ ] **Step 6: Add the idempotent `backfill` command**

Add `backfill --out web/public/papers.json --days 365 --per-topic 20`. It builds `llm_systems` with a 365-day arXiv window and one-year conference window, merges into existing history, marks selected papers `foundation=true`, stores the ordered review IDs, and sets `cold_start_completed_at` only after both JSON files are written successfully.

- [ ] **Step 7: Run tests and commit**

Run: `pytest tests/test_digest_state.py tests/test_foundations.py tests/test_pipeline.py -v`

Expected: all tests pass.

```bash
git add daily_paper/digest_state.py daily_paper/foundations.py daily_paper/cli.py tests/test_digest_state.py tests/test_foundations.py
git commit -m "feat: add foundations cold start"
```

### Task 8: Add track-aware email rendering and delivery

**Files:**
- Modify: `daily_paper/email_template.py`
- Modify: `daily_paper/cli.py`
- Modify: `tests/test_email_mailer.py`

**Interfaces:**
- Produces: `render_track_html(papers, track, title, foundation_papers=())`.
- Produces: `render_track_text(papers, track, title, foundation_papers=())`.
- Extends CLI: `preview/send --track llm_systems|generative_rec`.

- [ ] **Step 1: Write failing section tests**

```python
def test_llm_email_has_new_and_classic_sections():
    html = render_track_html([llm_paper("new")], llm_track(), "Daily", [llm_paper("classic")])
    assert "今日新论文" in html
    assert "经典回顾" in html
    assert "训练目标" in html

def test_gr_email_keeps_ab_evidence_without_classic_section():
    html = render_track_html([gr_paper()], gr_track(), "Weekly GR")
    assert "线上 A/B" in html
    assert "经典回顾" not in html
```

- [ ] **Step 2: Verify failure**

Run: `pytest tests/test_email_mailer.py -v`

Expected: missing track renderers.

- [ ] **Step 3: Implement separate render paths**

Render common bibliographic content once. For `llm_systems`, render topic badges, per-track score/rationale, and non-empty research details. For GR, keep current tags and A/B evidence. Append classics after the normal section and label each as a review.

- [ ] **Step 4: Advance delivery state only after send succeeds**

Select normal papers excluding `sent_ids[track]`; append the next foundation batch only for the first 20 successful primary sends. After `send_message` returns, add normal IDs, advance the foundation cursor, set last-success timestamp, and atomically save state. Dry-run renders but does not mutate state.

- [ ] **Step 5: Run tests and commit**

Run: `pytest tests/test_email_mailer.py tests/test_digest_state.py -v`

Expected: all tests pass.

```bash
git add daily_paper/email_template.py daily_paper/cli.py tests/test_email_mailer.py
git commit -m "feat: send track-specific digests"
```

### Task 9: Implement track and foundations views in the web application

**Files:**
- Create: `web/src/paper-utils.mjs`
- Create: `web/tests/paper-utils.test.mjs`
- Modify: `web/src/main.jsx`
- Modify: `web/src/styles.css`
- Modify: `web/package.json`

**Interfaces:**
- Produces: `papersForView(papers, track, topic, view)`, `trackScore(paper, track)`, and `trackTopics(papers, track)`.
- Consumes payload: `default_track`, `tracks`, canonical `papers`, and `foundation` flags.

- [ ] **Step 1: Write failing utility tests**

```javascript
import assert from "node:assert/strict";
import test from "node:test";
import { papersForView, trackScore } from "../src/paper-utils.mjs";

test("track and foundation views stay isolated", () => {
  const papers = [
    { id: "a", tracks: ["llm_systems"], topics: ["llm_rl"], foundation: true, track_scores: { llm_systems: 88 } },
    { id: "b", tracks: ["generative_rec"], topics: [], foundation: false, track_scores: { generative_rec: 77 } }
  ];
  assert.deepEqual(papersForView(papers, "llm_systems", "llm_rl", "foundations").map((p) => p.id), ["a"]);
  assert.equal(trackScore(papers[0], "llm_systems"), 88);
});
```

- [ ] **Step 2: Verify failure**

Run: `node --test web/tests/paper-utils.test.mjs`

Expected: module-not-found failure.

- [ ] **Step 3: Implement pure view utilities**

Filter by track membership first, then optional topic, then `foundation === true` for the foundations view. Sort by foundation score in foundations view and by the selected track score followed by publication date in latest view.

- [ ] **Step 4: Add the UI state and controls**

Initialize `activeTrack` from `payload.default_track`, reset topic/tag/A-B filters when switching track, and expose:

```jsx
<nav className="trackTabs" aria-label="研究频道">
  <button onClick={() => setActiveTrack("llm_systems")} className={activeTrack === "llm_systems" ? "active" : ""}>RL · Post-training · Agent</button>
  <button onClick={() => setActiveTrack("generative_rec")} className={activeTrack === "generative_rec" ? "active" : ""}>Generative Recommendation</button>
</nav>
```

Within `llm_systems`, add topic buttons and `每日最新/近一年经典`. Hide the A/B filter outside GR. Compute stats and the word cloud only from the active track/view.

- [ ] **Step 5: Render track-specific card evidence**

Display `track_scores[activeTrack]`, rationale, topic badges, and non-empty research-detail rows. Keep the existing A/B box only for GR cards. Preserve `MARKS_KEY` and paper-ID-based local state.

- [ ] **Step 6: Add responsive styles and package test command**

Set `"test": "node --test tests/*.test.mjs"` in `web/package.json`. Add accessible active states and ensure track/topic tabs wrap below 720px without horizontal overflow.

- [ ] **Step 7: Run tests/build and commit**

Run: `cd web && npm test && npm run build`

Expected: Node tests pass and esbuild exits 0.

```bash
git add web/src/paper-utils.mjs web/tests/paper-utils.test.mjs web/src/main.jsx web/src/styles.css web/package.json
git commit -m "feat: add research track dashboard"
```

### Task 10: Wire scheduling, generated state, and operations documentation

**Files:**
- Modify: `.github/workflows/daily-pages.yml`
- Modify: `scripts/build_pages.sh`
- Modify: `README.md`
- Create: `digest_state.json`
- Modify: `tests/test_state_config.py`

**Interfaces:**
- Daily workflow builds `llm_systems` and the site.
- Friday run additionally builds `generative_rec`.
- Workflow persists `web/public/papers.json`, `docs/papers.json`, and `digest_state.json`.
- Scheduled or explicitly approved dispatch runs may send email; ordinary push builds never send email.

- [ ] **Step 1: Write failing script/config assertions**

```python
def test_workflow_and_script_persist_state_without_push_email():
    workflow = Path(".github/workflows/daily-pages.yml").read_text(encoding="utf-8")
    script = Path("scripts/build_pages.sh").read_text(encoding="utf-8")
    assert "digest_state.json" in workflow
    assert "github.event_name == 'schedule'" in workflow
    assert "--track generative_rec" in script
    assert "DAILY_PAPER_SEND" in script
```

- [ ] **Step 2: Verify failure or incomplete production wiring**

Run: `pytest tests/test_state_config.py::test_workflow_and_script_persist_state_without_push_email -v`

Expected before wiring: assertions fail because state persistence, track scheduling, and the send gate are absent.

- [ ] **Step 3: Wire local and GitHub builds**

On first run without `cold_start_completed_at`, execute the idempotent 365-day backfill before normal site-data generation. Pass `--track llm_systems` daily. On Friday in Asia/Shanghai, also pass `--track generative_rec`. Persist the three generated state/data files in the workflow commit.

Guard email with `DAILY_PAPER_SEND=true`. The GitHub email step runs only when `github.event_name == 'schedule'` or a `workflow_dispatch` boolean input `send_email` is true. Supply recipient and SMTP values from `DAILY_PAPER_TO`, `SMTP_USER`, and repository secrets. A push event builds and deploys the site but never invokes `send`.

- [ ] **Step 4: Document operating commands**

Document `backfill`, per-track preview/send, Friday behavior, the three topic quotas, state recovery, and how to rebuild without API keys. Update the project description and site subtitle to the new primary focus.

- [ ] **Step 5: Run tests and shell syntax checks**

Run: `pytest tests/test_state_config.py -v && bash -n scripts/build_pages.sh`

Expected: all tests pass and shell syntax check exits 0.

- [ ] **Step 6: Commit**

```bash
git add .github/workflows/daily-pages.yml scripts/build_pages.sh README.md config.toml digest_state.json tests/test_state_config.py
git commit -m "chore: schedule daily and weekly tracks"
```

### Task 11: Full regression, generated-site verification, and acceptance audit

**Files:**
- Modify if verification exposes a defect: only the file owning that defect and its focused test.
- Generated: `web/public/papers.json`, `docs/index.html`, `docs/assets/app.js`, `docs/assets/app.css`, `docs/papers.json`.

**Interfaces:**
- Verifies every acceptance criterion in the approved design spec.

- [ ] **Step 1: Run the complete Python suite**

Run: `pytest -q`

Expected: zero failures.

- [ ] **Step 2: Run the complete web suite and build**

Run: `cd web && npm test && npm run build`

Expected: all Node tests pass and build exits 0; `docs/superpowers/specs` and `docs/superpowers/plans` still exist.

- [ ] **Step 3: Run offline CLI smoke tests**

Run with network functions mocked by the existing pytest fixtures: `pytest tests/test_pipeline.py tests/test_foundations.py tests/test_email_mailer.py -v`.

Expected: track isolation, 4/4/4 redistribution, 365-day idempotency, foundation review progression, and email sections pass.

- [ ] **Step 4: Audit the spec line by line**

Check the approved spec sections against tests and runtime behavior: taxonomy, 70 relevance gate, separate scores, daily/weekly cadence, canonical deduplication, failure isolation, legacy migration, foundations scoring/diversity, 20 review batches, UI isolation, and state-safe retries. Record any missing criterion as a failing test before changing code.

- [ ] **Step 5: Inspect final repository state**

Run: `git status --short && git log --oneline --decorate -12`

Expected: only intentional generated data changes remain, or the worktree is clean after the final focused commit.

- [ ] **Step 6: Commit generated assets only if they changed through the verified build**

```bash
git add web/public/papers.json docs/index.html docs/assets/app.js docs/assets/app.css docs/papers.json
git diff --cached --quiet || git commit -m "build: refresh research track site"
```
