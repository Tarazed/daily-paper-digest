import datetime as dt
import json
from dataclasses import asdict
from types import SimpleNamespace

from daily_paper.cli import _backfill_command
from daily_paper.config import load_config
from daily_paper.digest_state import DigestState
from daily_paper.foundations import (
    citation_velocity_points,
    foundation_score,
    next_foundation_batch,
    select_foundations,
)
from daily_paper.models import Paper
from daily_paper.pipeline import TrackBuildResult


def make_paper(
    paper_id,
    *,
    topic="llm_rl",
    citations=0,
    published="2026-07-01",
    title=None,
    authors=None,
    venue="",
):
    return Paper(
        id=paper_id,
        title=title or "Language Model Reinforcement Learning Method %s" % paper_id,
        authors=authors or ["Author %s" % paper_id],
        affiliations=[],
        published=published,
        updated=published,
        abstract="A language model training method with strong evidence.",
        categories=["cs.CL"],
        primary_category="cs.CL",
        abs_url="https://example.com/%s" % paper_id,
        pdf_url="",
        tracks=["llm_systems"],
        primary_track="llm_systems",
        topics=[topic],
        primary_topic=topic,
        track_relevance={"llm_systems": 90},
        track_score_breakdowns={
            "llm_systems": {
                "relevance": 27,
                "technical": 22,
                "evidence": 16,
                "novelty": 12,
                "reproducibility": 8,
            }
        },
        citation_count=citations,
        venue=venue,
    )


def test_foundation_score_normalizes_citations_by_age():
    now = dt.date(2026, 8, 27)
    old = make_paper("old", citations=100, published="2025-09-01")
    new = make_paper("new", citations=50, published="2026-07-01")

    assert citation_velocity_points(new, now) > citation_velocity_points(old, now)
    assert foundation_score(new, now) > foundation_score(old, now)


def test_select_foundations_keeps_up_to_twenty_per_topic():
    papers = []
    for topic in ("post_training", "llm_rl", "llm_agent"):
        papers.extend(
            make_paper("%s-%02d" % (topic, index), topic=topic, citations=30 - index)
            for index in range(23)
        )

    selected = select_foundations(papers, per_topic=20, now=dt.date(2026, 8, 27))

    assert len(selected) == 60
    for topic in ("post_training", "llm_rl", "llm_agent"):
        assert len([paper for paper in selected if paper.primary_topic == topic]) == 20
    assert all(paper.foundation for paper in selected)
    assert all(paper.foundation_score > 0 for paper in selected)


def test_diversity_report_does_not_relax_when_topic_has_fewer_candidates():
    report = {}

    selected = select_foundations(
        [make_paper("small-%s" % index) for index in range(3)],
        per_topic=20,
        now=dt.date(2026, 8, 27),
        report=report,
    )

    assert len(selected) == 3
    assert report["relaxations"] == {}


def test_select_foundations_limits_a_repeated_method_series_when_alternatives_exist():
    repeated = [
        make_paper(
            "series-%s" % index,
            citations=100 - index,
            title="Alpha-RL %s for Language Models" % index,
            authors=["Shared Author", "Coauthor %s" % index],
        )
        for index in range(10)
    ]
    alternatives = [
        make_paper(
            "alternative-%s" % index,
            citations=50 - index,
            title="Distinct Method %s for Language Model RL" % index,
            authors=["Alternative %s" % index],
        )
        for index in range(10)
    ]

    selected = select_foundations(
        repeated + alternatives, per_topic=10, now=dt.date(2026, 8, 27)
    )

    assert len([paper for paper in selected if paper.id.startswith("series-")]) <= 4


def test_next_batch_never_repeats_foundation():
    papers = [make_paper("p%s" % index) for index in range(1, 5)]
    state = DigestState(
        foundation_review_ids=["p1", "p2", "p3", "p4"],
        foundation_review_cursor=0,
    )

    first = next_foundation_batch(papers, state, 3)
    second = next_foundation_batch(papers, state, 3)

    assert [paper.id for paper in first] == ["p1", "p2", "p3"]
    assert [paper.id for paper in second] == ["p4"]
    assert state.foundation_review_cursor == 4


def test_twenty_review_batches_cover_sixty_foundations_once():
    papers = [make_paper("p%02d" % index) for index in range(60)]
    state = DigestState(foundation_review_ids=[paper.id for paper in papers])
    reviewed = []

    for _ in range(20):
        reviewed.extend(next_foundation_batch(papers, state, 3))

    assert len(reviewed) == 60
    assert len({paper.id for paper in reviewed}) == 60
    assert next_foundation_batch(papers, state, 3) == []


def test_foundation_report_records_missing_citations_and_relaxation_order():
    papers = [
        make_paper(
            "p%02d" % index,
            citations=0,
            title="Distinct Method %s for Language Models" % index,
            authors=["Shared Author"],
        )
        for index in range(20)
    ]
    report = {}

    selected = select_foundations(
        papers, per_topic=20, now=dt.date(2026, 8, 27), report=report
    )

    assert len(selected) == 20
    assert report["citation_unavailable"] == 20
    assert report["relaxations"]["llm_rl"] == [
        "publication_month",
        "author_group",
    ]


def test_backfill_writes_foundations_and_completion_state(tmp_path, monkeypatch):
    output_path = tmp_path / "papers.json"
    state_path = tmp_path / "digest_state.json"
    config = load_config("config.toml")
    config.digest_state_file = str(state_path)
    papers = [
        make_paper("post", topic="post_training", citations=10),
        make_paper("rl", topic="llm_rl", citations=20),
        make_paper("agent", topic="llm_agent", citations=30),
    ]
    observed = {}

    def fake_build(track_key, _config, **kwargs):
        observed.update({"track_key": track_key, **kwargs})
        return TrackBuildResult(track_key, papers, papers, [])

    monkeypatch.setattr("daily_paper.cli.build_track", fake_build)
    monkeypatch.setattr("daily_paper.cli.enrich_papers", lambda values, *args, **kwargs: values)

    result = _backfill_command(
        SimpleNamespace(out=str(output_path), days=365, per_topic=20), config
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert result == 0
    assert observed["track_key"] == "llm_systems"
    assert observed["days_back"] == 365
    assert observed["years_back"] == 1
    assert {paper["id"] for paper in payload["papers"] if paper["foundation"]} == {
        "post",
        "rl",
        "agent",
    }
    assert state["cold_start_completed_at"].endswith("Z")
    assert state["foundation_review_ids"] == ["post", "rl", "agent"]


def test_completed_backfill_is_idempotent(tmp_path, monkeypatch):
    state_path = tmp_path / "digest_state.json"
    state_path.write_text(
        json.dumps({"cold_start_completed_at": "2026-08-27T00:00:00Z"}),
        encoding="utf-8",
    )
    config = load_config("config.toml")
    config.digest_state_file = str(state_path)
    monkeypatch.setattr(
        "daily_paper.cli.build_track",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not fetch")),
    )

    result = _backfill_command(
        SimpleNamespace(out=str(tmp_path / "papers.json"), days=365, per_topic=20),
        config,
    )

    assert result == 0


def test_backfill_replaces_stale_foundation_membership(tmp_path, monkeypatch):
    output_path = tmp_path / "papers.json"
    state_path = tmp_path / "digest_state.json"
    stale = make_paper("stale", citations=50)
    stale.foundation = True
    stale.foundation_score = 99
    output_path.write_text(
        json.dumps({"papers": [asdict(stale)]}), encoding="utf-8"
    )
    config = load_config("config.toml")
    config.digest_state_file = str(state_path)
    current = make_paper("current", citations=60)
    monkeypatch.setattr(
        "daily_paper.cli.build_track",
        lambda track_key, _config, **kwargs: TrackBuildResult(
            track_key, [current], [current], []
        ),
    )
    monkeypatch.setattr("daily_paper.cli.enrich_papers", lambda values, *args, **kwargs: values)

    assert _backfill_command(
        SimpleNamespace(out=str(output_path), days=365, per_topic=1), config
    ) == 0

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    foundation_by_id = {paper["id"]: paper["foundation"] for paper in payload["papers"]}
    assert foundation_by_id == {"current": True, "stale": False}
