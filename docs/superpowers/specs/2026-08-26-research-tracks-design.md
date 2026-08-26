# Research Tracks and Cold-Start Design

## Summary

Daily Paper Digest will shift its primary focus from generative recommendation (GR) to LLM post-training, LLM reinforcement learning, and general LLM agents. The application will remain one project with shared acquisition, enrichment, analysis, storage, and presentation infrastructure, but research interests will become isolated tracks with independent retrieval rules, classification, scoring, quotas, schedules, and digest templates.

The new `llm_systems` track will update daily. The existing `generative_rec` track will remain available and update weekly. A one-time 365-day backfill will seed the new track before daily updates begin, including a curated 60-paper foundations collection and a 20-day classic-paper review sequence.

## Goals

- Make LLM post-training, LLM RL, and LLM agents the default daily research focus.
- Keep GR available as a lower-frequency research track without mixing it into the new ranking or quota.
- Reuse the current acquisition, metadata enrichment, full-text analysis, cache, archive, and web application.
- Store a paper once while allowing independent membership and scores in multiple tracks.
- Seed the new track with important work from the preceding 365 days before normal daily operation begins.
- Preserve existing GR history, local importance/read marks, notes, and reusable analysis.

## Non-goals

- Covering traditional control, robotics, or general-purpose reinforcement learning that is unrelated to large language models.
- Splitting GR into a separate repository or deployment.
- Rebuilding all historical GR analyses during migration.
- Treating tags as the main information boundary; tracks and topics determine the information flow.
- Building citation-based academic impact analytics beyond what is needed to rank cold-start candidates.

## Current-State Constraints

The current configuration has one arXiv profile, one conference profile, one global relevance filter, one score, and one final limit. Its filtering rules, LLM scoring prompt, tags, email copy, word cloud, and default page content are centered on recommendation systems. Adding RL and agent keywords to this single stream would cause the old GR preferences and the new research direction to compete for the same ranking and quota.

The design therefore introduces research tracks rather than expanding the existing flat tag list.

## Research Taxonomy

### Primary track: `llm_systems`

The user-facing name is **RL · Post-training · Agent**. It contains three primary topics.

#### `post_training`

- Training-data construction, filtering, and synthesis
- Supervised fine-tuning
- Preference optimization, including DPO, IPO, KTO, and related methods
- Reward models, verifiers, process rewards, and feedback modeling
- Distillation, self-training, and self-improvement
- Post-training evaluation and scaling studies

#### `llm_rl`

- RLHF and RLAIF
- PPO, GRPO, and related optimization algorithms
- Reinforcement learning for reasoning
- Reinforcement learning for agents
- Reward hacking, exploration, and credit assignment
- Long-horizon and sparse-reward language-model tasks

#### `llm_agent`

- Planning and reasoning
- Tool use and function calling
- Memory and context management
- Multi-agent systems
- Environment interaction and computer use
- Agent training, evaluation, reliability, and safety

### Secondary track: `generative_rec`

The user-facing name remains **Generative Recommendation**. It retains the existing areas:

- Generative recommendation, retrieval, and ranking
- Semantic IDs and item tokenization
- LLM4Rec and Agent4Rec
- User modeling

### Classification rules

A paper may have multiple `tracks` and multiple `topics`, but it has one `primary_track` and one `primary_topic` for grouping and quota accounting.

- If the central contribution is a training or optimization method, use `post_training` or `llm_rl` as the primary topic.
- If the central contribution is an agent architecture, capability, interaction mechanism, or evaluation, use `llm_agent` as the primary topic.
- If the task explicitly serves recommendation, also assign `generative_rec` membership.
- A cross-track paper is stored once and receives an independent score in each assigned track.
- Traditional RL papers without a material LLM component do not pass the `llm_systems` relevance gate.

Track classification produces a 0–100 relevance value plus a short evidence string. A paper enters a public track archive at 70 or above. Values below 70 remain outside that track. When LLM classification is unavailable, the deterministic fallback requires at least one topic-specific positive phrase, no hard exclusion phrase, and an explicit LLM or language-model context; fallback matches that satisfy all three conditions receive the minimum passing relevance value of 70.

## Data Model

Shared bibliographic and analysis fields remain on `Paper`. Track-specific classification and scores are added without duplicating the paper.

```text
Paper
├── tracks: ["llm_systems", "generative_rec"]
├── primary_track: "llm_systems"
├── topics: ["llm_rl", "llm_agent"]
├── primary_topic: "llm_rl"
├── track_scores:
│   ├── llm_systems: 87
│   └── generative_rec: 61
├── foundation: true
├── foundation_score: 84
└── classification_version: "..."
```

Track membership, topic membership, and per-track scores must serialize into the site JSON. Old JSON records that lack these fields are interpreted as `generative_rec` records. Existing local marks continue to use the stable paper ID.

## Configuration Model

The single-domain configuration becomes a set of track profiles. Each profile owns its schedule, sources, relevance rules, scoring profile, and quota.

```toml
[tracks.llm_systems]
enabled = true
cadence = "daily"
quota = 12
categories = ["cs.CL", "cs.AI", "cs.LG", "cs.MA"]

[tracks.llm_systems.topic_quotas]
post_training = 4
llm_rl = 4
llm_agent = 4

[tracks.generative_rec]
enabled = true
cadence = "weekly"
weekly_day = "friday"
quota = 10
```

The implementation may preserve backward-compatible parsing for the current `[arxiv]` and `[dblp]` sections during migration, but the new track profiles are authoritative after migration.

## Sources and Candidate Retrieval

### `llm_systems`

- Search arXiv categories `cs.CL`, `cs.AI`, `cs.LG`, and `cs.MA` with topic-specific queries.
- Search ICLR, ICML, NeurIPS, ACL, EMNLP, NAACL, AAAI, IJCAI, and COLM through the existing conference-source abstraction.
- Use positive topic phrases and explicit negative rules to exclude unrelated robotics, control, and traditional RL papers.
- Keep topic query sets separate so one broad phrase such as “agent” cannot dominate the candidate pool.

### `generative_rec`

- Keep the current recommendation categories, terms, and venues.
- Continue using the GR-specific conference and fallback-source behavior.

Candidates from all profiles are normalized and globally deduplicated before expensive enrichment or analysis. arXiv IDs are the preferred key for arXiv papers, followed by DOI and a normalized title/year fallback.

## Processing Pipeline

```text
Fetch candidates per track and topic
→ Normalize identifiers and deduplicate globally
→ Apply deterministic track relevance gates
→ Classify tracks, topics, and primary topic
→ Enrich shared metadata
→ Generate or reuse shared summary and full-text analysis
→ Compute independent per-track scores
→ Apply track and topic quotas
→ Publish archive data and the scheduled digest
```

The summary, authors, affiliations, bibliographic metadata, extracted full text, and general analysis are shared. Classification, score rationale, and selection are track-specific. Cache signatures include classification, scoring, prompt, and analysis versions so a rule change invalidates only affected results.

## Daily `llm_systems` Ranking

The daily score is out of 100:

| Dimension | Points | Meaning |
| --- | ---: | --- |
| Direction relevance | 30 | Direct relevance to one or more of the three topics |
| Technical contribution | 25 | Substantive algorithmic, training, or agent-mechanism contribution |
| Experimental evidence | 20 | Strong baselines, ablations, scale, and task coverage |
| Novelty | 15 | Meaningful change relative to prior methods |
| Reproducibility and practical value | 10 | Code, data, models, training detail, or deployment value |

Online A/B tests, recommendation relevance, and internet-company affiliations do not contribute to the `llm_systems` score. They may remain part of the GR scoring profile.

The daily digest selects 12 new papers, reserving four places for each primary topic. If a topic has fewer than four eligible papers, its unused places go to the highest-scoring eligible papers from the other topics. A cross-topic paper appears once and consumes the quota of its primary topic.

All papers that pass the relevance gate remain in the website archive even when they do not enter the digest.

## Weekly GR Ranking

GR keeps a separate score and selects ten papers each Friday. Its scoring may continue to value online A/B evidence, recommendation-specific methods, top recommendation venues, Semantic ID relevance, and industrial evidence. GR scores never influence `llm_systems` selection.

## Cold Start and 365-Day Backfill

### Backfill window

Before the first daily digest, run a one-time retrieval for the preceding 365 calendar days using the same `llm_systems` track profiles. Normalize, deduplicate, classify, and metadata-score the entire candidate set. Every candidate that passes the normal track relevance gate is added to the website archive with its original publication date.

Backfill publication is idempotent: rerunning it updates matching records instead of creating duplicate papers or resetting local state.

### Foundations collection

Select 20 foundation papers per primary topic, for a target collection of 60. Cross-topic papers count against their primary-topic allocation but retain all topic labels. A diversity pass prevents a single model family, author group, month, or method series from dominating a topic list.

For each 20-paper topic allocation, the diversity pass normally allows at most four papers from the same named model or method series, three papers from the same recurring author group, and six papers from the same publication month. A constraint is relaxed only when enforcing it would leave the topic below 20 despite eligible candidates; relax month, then author group, then model/method series, in that order, and record the relaxation in the build report.

Foundation score is out of 100:

| Dimension | Points | Meaning |
| --- | ---: | --- |
| Direction relevance | 25 | Centrality to the selected LLM topic |
| Technical or foundational contribution | 25 | Methodological importance or enabling role |
| Experimental evidence | 15 | Reliability and breadth of reported evidence |
| Citation velocity or downstream adoption | 15 | Time-normalized citations or clear use by later work |
| Reproducibility | 10 | Available code, models, data, or sufficient detail |
| Venue or community recognition | 10 | Selective venue or other credible recognition |

Citation velocity uses the available OpenAlex or Semantic Scholar metadata and is normalized by paper age. Missing citation data contributes zero to that dimension and is recorded as unavailable; it does not prevent selection when the other dimensions are strong. The selector must not use cumulative citations alone.

The top foundation candidates receive the full site analysis. Lower-ranked backfill papers may initially use metadata analysis and be upgraded lazily when opened, marked important, or selected later.

### Launch sequence

- The website exposes the entire foundations collection at launch under **近一年经典**.
- For the first 20 successful daily runs, the daily email contains an additional **经典回顾** section with three previously unsent foundation papers.
- These three papers do not consume the 12 new-paper places.
- A foundation paper is sent in the review section at most once. Progress is stored durably so failed or repeated workflow runs do not skip or duplicate entries.
- After 20 successful review batches, the email returns to the normal 12-paper format. The foundations collection remains available on the website.

## Website Experience

The default top-level tab is **RL · Post-training · Agent**. **Generative Recommendation** is the secondary tab.

Within the primary tab, users can filter by Post-training, LLM RL, and LLM Agent. Each track computes its own paper count, topic distribution, keyword cloud, and ordering. Track statistics are never calculated from the combined corpus.

The primary track also exposes two views:

- **每日最新** for normal daily candidates and archive browsing
- **近一年经典** for the 60 foundation papers

Paper cards retain the summary, core method, innovation points, experiment results, limitations, and practical value. New-track cards additionally surface training objective, feedback or reward source, model/data scale, key benchmarks, and code/model availability. Agent papers surface environment, tools, memory/planning mechanism, interaction horizon, and agent evaluation. GR cards continue to emphasize recommendation metrics and online A/B evidence.

Importance, saved, and read marks remain keyed by paper ID and therefore persist across tracks and views.

## Email and Scheduling

- Every day at 08:00 Asia/Shanghai: build the primary track, update the site, and send the 12-paper daily digest.
- During the first 20 successful daily runs: append three foundation papers to the daily digest.
- Every Friday at 08:00 Asia/Shanghai: build and send the ten-paper GR weekly digest.
- Daily and weekly emails have distinct subjects and templates and never combine their ranked sections.

The daily candidate window starts at the last successful `llm_systems` run and is capped at the preceding seven days for outage recovery. The GR candidate window starts at the last successful GR run and is capped at the preceding 14 days. Papers already sent in a track's normal digest section cannot be selected there again. If fewer eligible new papers exist, the digest is shorter; it is not padded with stale or low-relevance work.

The scheduler records the last successful run per track, sent-paper IDs per track, and the cold-start review position. Re-running a workflow for the same logical period is safe and does not resend or advance state unless the send succeeds.

## Failure Handling

- A source failure is logged and the remaining configured sources continue.
- A track failure does not block another track's build or scheduled digest.
- If one daily topic has too few eligible papers, unused places are reassigned rather than filled with low-relevance papers.
- If classification is unavailable, deterministic keyword classification provides a conservative fallback and the record notes the fallback basis.
- If citation providers fail during cold start, foundations selection continues without citation points and reports reduced evidence.
- If full-text analysis fails, metadata analysis is used and can be upgraded later.
- Existing archive data remains publishable when a scheduled fetch fails; the UI must not replace a valid archive with an empty result.

## Migration

1. Add backward-compatible track and topic fields to the paper model and serializer.
2. Interpret existing papers as `generative_rec` without changing stable IDs.
3. Preserve existing analysis, importance, read status, notes, and browser-local marks.
4. Move GR-specific relevance and score rules into the GR profile.
5. Introduce the new `llm_systems` profile and track-specific analysis prompts.
6. Run the 365-day backfill before enabling the first primary-track email.
7. Enable the daily primary schedule and Friday GR schedule only after the backfill state is durable.

## Verification and Acceptance Criteria

Automated verification must cover:

- RLHF, GRPO, reward-model, SFT, tool-use, and agent-memory papers classify into the expected topics.
- Traditional robotics and control RL papers do not enter `llm_systems` without a material LLM contribution.
- Cross-topic and cross-track papers are stored once with independent membership and scores.
- The 4/4/4 allocation, cross-topic deduplication, and empty-topic redistribution are correct.
- Only papers with track relevance of at least 70 enter the public archive, including under deterministic fallback.
- GR ranking signals cannot alter `llm_systems` scores.
- Backfill is idempotent and uses the preceding 365 calendar days.
- Foundations selection produces up to 20 papers per topic, applies the defined diversity caps and relaxation order, and normalizes citation velocity by age.
- The first 20 successful daily sends contain three unique foundation papers and do not reduce the 12 new-paper quota.
- Failed or repeated workflow runs do not advance or duplicate the foundation review sequence.
- Daily and weekly candidate windows recover from short outages without resending previously delivered normal-section papers.
- Old GR records, analysis caches, state-file values, and local browser marks remain usable.
- The website defaults to the primary track and keeps track statistics, filters, archives, and foundation views isolated.
- Daily and weekly email templates render the correct sections and quotas.
- Failure in one source or track does not erase the existing archive or block an unrelated track.

## Approved Defaults

- Architecture: one project with shared infrastructure and isolated research tracks.
- Primary scope: complete LLM post-training, LLM-specific RL, and general LLM agent methods.
- Secondary scope: existing GR interests.
- Primary cadence: daily at 08:00 Asia/Shanghai, 12 new papers using a 4/4/4 topic allocation.
- GR cadence: Friday at 08:00 Asia/Shanghai, 10 papers.
- Cold start: 365-day backfill, 60-paper foundations target, and three classic reviews per day for 20 successful daily runs.
