from daily_paper.config import load_config
from daily_paper.models import Paper
from daily_paper.pipeline import TrackBuildResult, build_site_payload, build_track


def make_paper(paper_id, title, abstract):
    return Paper(
        id=paper_id,
        title=title,
        authors=["Alice"],
        affiliations=[],
        published="2026-08-20T00:00:00Z",
        updated="2026-08-20T00:00:00Z",
        abstract=abstract,
        categories=["cs.CL"],
        primary_category="cs.CL",
        abs_url="https://arxiv.org/abs/%s" % paper_id,
        pdf_url="https://arxiv.org/pdf/%s" % paper_id,
    )


def test_build_track_keeps_scores_isolated(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    config = load_config("config.toml")
    paper = make_paper(
        "arxiv:cross",
        "LLM Agent for Generative Recommendation",
        "A language model agent plans tool use for recommendation.",
    )

    result = build_track(
        "llm_systems",
        config,
        previous_papers=[],
        paper_state={},
        fetch_arxiv=lambda _: [paper],
        fetch_conferences=lambda _: [],
    )

    assert [item.id for item in result.papers] == ["arxiv:cross"]
    assert "llm_systems" in result.papers[0].tracks
    assert "generative_rec" not in result.papers[0].track_scores


def test_site_payload_keeps_one_cross_track_record():
    config = load_config("config.toml")
    llm = make_paper("arxiv:cross", "Cross-track paper", "Language model agent.")
    llm.tracks = ["llm_systems"]
    llm.primary_track = "llm_systems"
    llm.topics = ["llm_agent"]
    llm.primary_topic = "llm_agent"
    llm.track_relevance = {"llm_systems": 90}
    llm.track_scores = {"llm_systems": 88}
    gr = make_paper("arxiv:cross", "Cross-track paper", "Recommendation agent.")
    gr.tracks = ["generative_rec"]
    gr.primary_track = "generative_rec"
    gr.track_relevance = {"generative_rec": 82}
    gr.track_scores = {"generative_rec": 77}
    results = [
        TrackBuildResult("llm_systems", [llm], [llm], []),
        TrackBuildResult("generative_rec", [gr], [gr], []),
    ]

    payload = build_site_payload(results, previous_papers=[], config=config)

    assert [paper["id"] for paper in payload["papers"]] == ["arxiv:cross"]
    assert payload["papers"][0]["tracks"] == ["llm_systems", "generative_rec"]
    assert payload["papers"][0]["track_scores"] == {
        "llm_systems": 88,
        "generative_rec": 77,
    }
    assert payload["default_track"] == "llm_systems"
    assert payload["tracks"]["llm_systems"]["paper_ids"] == ["arxiv:cross"]


def test_build_track_uses_cached_track_when_both_sources_fail(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    config = load_config("config.toml")
    cached = make_paper(
        "arxiv:cached",
        "Cached LLM Agent",
        "A language model agent uses tools.",
    )
    cached.tracks = ["llm_systems"]
    cached.primary_track = "llm_systems"
    cached.topics = ["llm_agent"]
    cached.primary_topic = "llm_agent"
    cached.track_relevance = {"llm_systems": 80}
    cached.track_scores = {"llm_systems": 70}

    def fail(_):
        raise RuntimeError("source unavailable")

    result = build_track(
        "llm_systems",
        config,
        previous_papers=[cached],
        paper_state={},
        fetch_arxiv=fail,
        fetch_conferences=fail,
    )

    assert [paper.id for paper in result.papers] == ["arxiv:cached"]
    assert len(result.source_errors) == 2
