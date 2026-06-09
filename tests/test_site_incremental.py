import json
from dataclasses import asdict

from daily_paper.cli import _load_previous_site_papers, _reuse_cached_site_analysis
from daily_paper.config import SummaryConfig
from daily_paper.models import Paper
from daily_paper.summarizer import expected_analysis_signature


def make_summary_config():
    return SummaryConfig(
        provider="deepseek",
        base_url="https://api.deepseek.com",
        model="deepseek-v4-flash",
        analysis_model="deepseek-v4-pro",
        language="zh",
        max_sentences=3,
        full_text_max_chars=12000,
        full_text_timeout_seconds=10,
        analysis_workers=1,
    )


def make_paper(paper_id, title="LLM4Rec for Sequential Recommendation"):
    return Paper(
        id=paper_id,
        title=title,
        authors=["Alice Zhang"],
        affiliations=["Tsinghua University"],
        published="2026-06-07T00:00:00Z",
        updated="2026-06-07T00:00:00Z",
        abstract="We propose an LLM4Rec method for sequential recommendation.",
        categories=["cs.IR"],
        primary_category="cs.IR",
        abs_url="https://arxiv.org/abs/2606.01234",
        pdf_url="https://arxiv.org/pdf/2606.01234",
    )


def add_complete_analysis(paper, config):
    paper.generated_summary = "深度摘要"
    paper.core_method = "核心方法"
    paper.innovation_points = ["创新点"]
    paper.experiment_results = ["实验结果"]
    paper.ab_test = "no"
    paper.ab_test_evidence = "论文全文未报告线上 A/B 测试。"
    paper.limitations = ["局限"]
    paper.practical_value = "实践价值"
    paper.analysis_basis = "full_text"
    paper.analysis_status = "complete"
    paper.analysis_signature = expected_analysis_signature(paper, config)
    paper.tags = ["LLM4Rec"]
    return paper


def test_reuse_cached_site_analysis_skips_unchanged_paper():
    config = make_summary_config()
    previous = add_complete_analysis(make_paper("arxiv:2606.01234"), config)
    current = make_paper("arxiv:2606.01234")

    to_analyze = _reuse_cached_site_analysis([current], [previous], config)

    assert to_analyze == []
    assert current.generated_summary == "深度摘要"
    assert current.analysis_status == "cached"
    assert current.innovation_points == ["创新点"]


def test_reuse_cached_site_analysis_reanalyzes_updated_paper():
    config = make_summary_config()
    previous = add_complete_analysis(make_paper("arxiv:2606.01234"), config)
    current = make_paper("arxiv:2606.01234")
    current.updated = "2026-06-08T00:00:00Z"

    to_analyze = _reuse_cached_site_analysis([current], [previous], config)

    assert to_analyze == [current]
    assert current.generated_summary == ""


def test_reuse_cached_site_analysis_accepts_legacy_complete_analysis():
    config = make_summary_config()
    previous = add_complete_analysis(make_paper("arxiv:2606.01234"), config)
    previous.analysis_status = ""
    previous.analysis_signature = ""
    current = make_paper("arxiv:2606.01234")

    to_analyze = _reuse_cached_site_analysis([current], [previous], config)

    assert to_analyze == []
    assert current.generated_summary == "深度摘要"
    assert current.analysis_status == "cached"
    assert current.analysis_signature == expected_analysis_signature(current, config)


def test_load_previous_site_papers_reads_existing_payload(tmp_path):
    path = tmp_path / "papers.json"
    paper = make_paper("arxiv:2606.01234")
    path.write_text(json.dumps({"papers": [asdict(paper)]}), encoding="utf-8")

    loaded = _load_previous_site_papers(str(path))

    assert [paper.id for paper in loaded] == ["arxiv:2606.01234"]
