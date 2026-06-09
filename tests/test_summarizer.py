import json

from daily_paper.models import Paper
from daily_paper.summarizer import ChatCompletionClient, analyze_papers_for_site, summarize_papers
from daily_paper.config import SummaryConfig


def make_paper():
    return Paper(
        id="arxiv:2606.01234",
        title="LLM4Rec for Sequential Recommendation",
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


def test_deepseek_chat_completion_payload(monkeypatch):
    captured = {}
    response_payload = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {"summary": "这篇论文研究 LLM4Rec。", "tags": ["LLM4Rec", "RecSys"]}
                    )
                }
            }
        ]
    }

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(response_payload).encode("utf-8")

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["authorization"] = request.headers["Authorization"]
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    client = ChatCompletionClient(
        api_key="secret",
        base_url="https://api.deepseek.com",
        model="deepseek-v4-flash",
        provider="deepseek",
    )
    result = client.summarize(make_paper())

    assert captured["url"] == "https://api.deepseek.com/chat/completions"
    assert captured["authorization"] == "Bearer secret"
    assert captured["body"]["model"] == "deepseek-v4-flash"
    assert captured["body"]["response_format"] == {"type": "json_object"}
    assert captured["body"]["thinking"] == {"type": "disabled"}
    assert result["tags"] == ["LLM4Rec", "RecSys"]


def test_summarize_papers_uses_deepseek_api_key(monkeypatch):
    paper = make_paper()

    def fake_summarize(self, paper, language="zh"):
        return {"summary": "模型摘要", "tags": ["LLM4Rec"]}

    monkeypatch.setenv("DEEPSEEK_API_KEY", "secret")
    monkeypatch.setattr(ChatCompletionClient, "summarize", fake_summarize)

    summarize_papers(
        [paper],
        SummaryConfig(
            provider="deepseek",
            base_url="https://api.deepseek.com",
            model="deepseek-v4-flash",
            analysis_model="deepseek-v4-pro",
            language="zh",
            max_sentences=3,
            full_text_max_chars=12000,
            full_text_timeout_seconds=10,
            analysis_workers=1,
        ),
    )

    assert paper.generated_summary == "模型摘要"
    assert paper.tags == ["LLM4Rec"]


def test_summarize_papers_parallel_applies_all_results(monkeypatch):
    papers = [make_paper(), make_paper()]
    papers[1].id = "arxiv:2606.05678"
    calls = []

    def fake_summarize(self, paper, language="zh"):
        calls.append(paper.id)
        return {"summary": "模型摘要 " + paper.id, "tags": ["LLM4Rec"]}

    monkeypatch.setenv("DEEPSEEK_API_KEY", "secret")
    monkeypatch.setattr(ChatCompletionClient, "summarize", fake_summarize)

    summarize_papers(
        papers,
        SummaryConfig(
            provider="deepseek",
            base_url="https://api.deepseek.com",
            model="deepseek-v4-flash",
            analysis_model="deepseek-v4-pro",
            language="zh",
            max_sentences=3,
            full_text_max_chars=12000,
            full_text_timeout_seconds=10,
            analysis_workers=1,
            summary_workers=2,
        ),
    )

    assert sorted(calls) == ["arxiv:2606.01234", "arxiv:2606.05678"]
    assert [paper.generated_summary for paper in papers] == [
        "模型摘要 arxiv:2606.01234",
        "模型摘要 arxiv:2606.05678",
    ]


def test_analyze_papers_for_site_uses_analysis_model(monkeypatch):
    paper = make_paper()
    models = []

    def fake_summarize(self, paper, language="zh"):
        models.append(self.model)
        return {"summary": "轻量摘要", "tags": ["LLM4Rec"]}

    def fake_analyze(self, paper, full_text="", language="zh"):
        models.append(self.model)
        assert full_text == "full paper text"
        return {
            "summary": "深度摘要",
            "innovation_points": ["提出面向推荐的 LLM 方法"],
            "experiment_results": ["在序列推荐任务上优于基线"],
            "ab_test": "unknown",
            "ab_test_evidence": "摘要未提及线上 A/B 测试。",
            "limitations": ["需要阅读全文确认数据集。"],
            "practical_value": "可用于 LLM4Rec 方法设计参考。",
            "tags": ["LLM4Rec", "RecSys"],
        }

    monkeypatch.setenv("DEEPSEEK_API_KEY", "secret")
    monkeypatch.setattr(ChatCompletionClient, "summarize", fake_summarize)
    monkeypatch.setattr(ChatCompletionClient, "analyze_for_site", fake_analyze)
    monkeypatch.setattr("daily_paper.summarizer.extract_full_text_for_analysis", lambda *args, **kwargs: "full paper text")

    analyze_papers_for_site(
        [paper],
        SummaryConfig(
            provider="deepseek",
            base_url="https://api.deepseek.com",
            model="deepseek-v4-flash",
            analysis_model="deepseek-v4-pro",
            language="zh",
            max_sentences=3,
            full_text_max_chars=12000,
            full_text_timeout_seconds=10,
            analysis_workers=1,
        ),
    )

    assert models == ["deepseek-v4-flash", "deepseek-v4-pro"]
    assert paper.generated_summary == "深度摘要"
    assert paper.innovation_points == ["提出面向推荐的 LLM 方法"]
    assert paper.experiment_results == ["在序列推荐任务上优于基线"]
    assert paper.ab_test == "no"
    assert paper.analysis_basis == "full_text"


def test_analyze_papers_for_site_parallel_applies_all_results(monkeypatch):
    papers = [make_paper(), make_paper()]
    papers[1].id = "arxiv:2606.05678"
    calls = []

    def fake_summarize(self, paper, language="zh"):
        return {"summary": "轻量摘要", "tags": ["LLM4Rec"]}

    def fake_analyze(self, paper, full_text="", language="zh"):
        calls.append(paper.id)
        return {
            "summary": "深度摘要 " + paper.id,
            "core_method": "核心方法",
            "innovation_points": ["创新点"],
            "experiment_results": ["实验结果"],
            "ab_test": "unknown",
            "tags": ["LLM4Rec"],
        }

    monkeypatch.setenv("DEEPSEEK_API_KEY", "secret")
    monkeypatch.setattr(ChatCompletionClient, "summarize", fake_summarize)
    monkeypatch.setattr(ChatCompletionClient, "analyze_for_site", fake_analyze)
    monkeypatch.setattr("daily_paper.summarizer.extract_full_text_for_analysis", lambda *args, **kwargs: "full paper text")

    analyze_papers_for_site(
        papers,
        SummaryConfig(
            provider="deepseek",
            base_url="https://api.deepseek.com",
            model="deepseek-v4-flash",
            analysis_model="deepseek-v4-pro",
            language="zh",
            max_sentences=3,
            full_text_max_chars=12000,
            full_text_timeout_seconds=10,
            analysis_workers=2,
        ),
    )

    assert sorted(calls) == ["arxiv:2606.01234", "arxiv:2606.05678"]
    assert all(paper.core_method == "核心方法" for paper in papers)
    assert all(paper.ab_test == "no" for paper in papers)
