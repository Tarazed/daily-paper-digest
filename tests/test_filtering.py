from daily_paper.config import ArxivConfig
from daily_paper.filtering import infer_tags, prepare_papers
from daily_paper.models import Paper


def make_paper(paper_id, title, abstract):
    return Paper(
        id=paper_id,
        title=title,
        authors=["Alice"],
        affiliations=[],
        published="2026-06-07T00:00:00Z",
        updated="2026-06-07T00:00:00Z",
        abstract=abstract,
        categories=["cs.IR"],
        primary_category="cs.IR",
        abs_url="https://arxiv.org/abs/2606.00001",
        pdf_url="https://arxiv.org/pdf/2606.00001",
    )


def config():
    return ArxivConfig(
        categories=["cs.IR"],
        include_keywords=["recommendation", "LLM4Rec", "Agent4Rec"],
        exclude_keywords=["advertising"],
        max_results=10,
        days_back=14,
    )


def test_prepare_papers_filters_excludes_and_applies_state():
    important = make_paper(
        "arxiv:1",
        "Agent4Rec for Recommender Systems",
        "A recommendation agent method.",
    )
    excluded = make_paper(
        "arxiv:2",
        "Advertising Recommendation",
        "A sponsored advertising recommendation paper.",
    )

    papers = prepare_papers(
        [excluded, important],
        config(),
        {"arxiv:1": {"importance": "high", "read_status": "saved", "notes": "Read first"}},
    )

    assert [paper.id for paper in papers] == ["arxiv:1"]
    assert papers[0].importance == "high"
    assert papers[0].read_status == "saved"
    assert "Agent4Rec" in papers[0].tags


def test_infer_tags_for_llm4rec_and_benchmark():
    paper = make_paper(
        "arxiv:3",
        "LLM4Rec Benchmark",
        "A benchmark for large language model based recommendation evaluation.",
    )

    assert infer_tags(paper) == ["LLM4Rec", "RecSys", "Evaluation", "Benchmark"]
