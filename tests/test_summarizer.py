import json

from daily_paper.models import Paper
from daily_paper.summarizer import (
    ChatCompletionClient,
    analyze_papers_for_site,
    classify_and_score_track,
    score_papers_with_llm,
    summarize_papers,
)
from daily_paper.config import SummaryConfig, load_config


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


def test_deepseek_chat_completion_payload(monkeypatch):
    captured = {}
    response_payload = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {"summary": "这篇论文研究 LLM4Rec。", "tags": ["LLM4Rec", "Sequential Rec"]}
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
    assert "Semantic ID" in captured["body"]["messages"][0]["content"]
    assert result["tags"] == ["LLM4Rec", "Sequential Rec"]


def test_preference_scoring_payload(monkeypatch):
    captured = {}
    response_payload = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "score": 92,
                            "signals": ["Online A/B", "Generative Rec / Semantic ID"],
                            "reasons": ["有线上 A/B 测试", "语义 ID 推荐相关"],
                        }
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
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    client = ChatCompletionClient(
        api_key="secret",
        base_url="https://api.deepseek.com",
        model="deepseek-v4-pro",
        provider="deepseek",
    )
    result = client.score_preference(make_paper())

    assert captured["body"]["response_format"] == {"type": "json_object"}
    assert "线上 A/B" in captured["body"]["messages"][0]["content"]
    assert result["score"] == 92


def test_track_scoring_payload_uses_confirmed_dimensions(monkeypatch):
    captured = {}
    response_payload = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "track_relevance": 94,
                            "topics": ["llm_rl"],
                            "primary_topic": "llm_rl",
                            "evidence_text": "GRPO with verifiable rewards",
                            "score_breakdown": {
                                "relevance": 29,
                                "technical": 24,
                                "evidence": 18,
                                "novelty": 14,
                                "reproducibility": 9,
                            },
                            "rationale": "Strong LLM RL contribution.",
                            "research_details": {
                                "feedback_source": "verifiable rewards"
                            },
                        }
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
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    paper = make_paper()
    paper.title = "GRPO for Language Model Reasoning"
    paper.abstract = "We optimize a language model with verifiable rewards."
    client = ChatCompletionClient("secret", "https://api.deepseek.com", "deepseek-v4-pro")

    result = client.classify_and_score_track(paper, "llm_systems")

    prompt = captured["body"]["messages"][0]["content"]
    assert "relevance 0-30" in prompt
    assert "technical 0-25" in prompt
    assert result["primary_topic"] == "llm_rl"


def test_classify_and_score_track_applies_llm_result(monkeypatch):
    paper = make_paper()
    paper.title = "GRPO for Language Model Reasoning"
    paper.abstract = "We optimize a language model with verifiable rewards."
    track = load_config("config.toml").tracks["llm_systems"]

    def fake_score(self, paper, track_key, language="zh"):
        return {
            "track_relevance": 94,
            "topics": ["llm_rl"],
            "primary_topic": "llm_rl",
            "evidence_text": "GRPO with verifiable rewards",
            "score_breakdown": {
                "relevance": 29,
                "technical": 24,
                "evidence": 18,
                "novelty": 14,
                "reproducibility": 9,
            },
            "rationale": "Strong LLM RL contribution.",
            "research_details": {"feedback_source": "verifiable rewards"},
        }

    monkeypatch.setenv("DEEPSEEK_API_KEY", "secret")
    monkeypatch.setattr(ChatCompletionClient, "classify_and_score_track", fake_score)

    classify_and_score_track([paper], track, make_summary_config())

    assert paper.tracks == ["llm_systems"]
    assert paper.primary_topic == "llm_rl"
    assert paper.track_scores["llm_systems"] == 94
    assert paper.research_details["feedback_source"] == "verifiable rewards"


def test_classify_and_score_track_falls_back_without_api_key(monkeypatch):
    paper = make_paper()
    paper.title = "GRPO for Language Model Reasoning"
    paper.abstract = "We optimize a language model with verifiable rewards."
    track = load_config("config.toml").tracks["llm_systems"]
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    classify_and_score_track([paper], track, make_summary_config())

    assert paper.track_relevance["llm_systems"] >= 70
    assert paper.primary_topic == "llm_rl"
    assert paper.track_scores["llm_systems"] > 0


def test_score_papers_with_llm_applies_preference_score(monkeypatch):
    paper = make_paper()

    def fake_score(self, paper, language="zh"):
        return {
            "score": 87,
            "signals": ["Online A/B", "Industry company"],
            "reasons": ["报告线上 A/B 测试", "作者单位包含互联网公司"],
        }

    monkeypatch.setenv("DEEPSEEK_API_KEY", "secret")
    monkeypatch.setattr(ChatCompletionClient, "score_preference", fake_score)

    score_papers_with_llm(
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

    assert paper.llm_score == 87
    assert paper.score == 87
    assert paper.preference_signals == ["Online A/B", "Industry company"]
    assert "线上 A/B" in paper.llm_score_rationale


def test_score_papers_with_llm_falls_back_without_api_key(monkeypatch):
    paper = make_paper()
    paper.title = "Semantic ID for Generative Recommendation"
    paper.abstract = "We run an online A/B test on live traffic."
    paper.venue = "KDD"
    paper.venue_key = "KDD"
    paper.affiliations = ["Microsoft"]
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    score_papers_with_llm(
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

    assert paper.llm_score == 100
    assert "Online A/B" in paper.preference_signals
    assert "Top venue" in paper.preference_signals


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
            "tags": ["LLM4Rec", "Semantic ID"],
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
    assert paper.tags == ["LLM4Rec", "Semantic ID"]


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


def test_llm_site_analysis_keeps_research_details_without_forcing_ab(monkeypatch):
    paper = make_paper()
    paper.title = "Tool-Using Language Model Agent"
    paper.abstract = "A language model agent plans and calls tools."
    paper.tracks = ["llm_systems"]
    paper.primary_track = "llm_systems"
    paper.topics = ["llm_agent"]
    paper.primary_topic = "llm_agent"

    def fake_summarize(self, paper, language="zh"):
        return {"summary": "轻量摘要", "tags": []}

    def fake_analyze(self, paper, full_text="", language="zh"):
        return {
            "summary": "Agent 深度摘要",
            "core_method": "规划器调用工具并写入记忆",
            "innovation_points": ["长时程工具规划"],
            "experiment_results": ["在 Agent 基准上提升"],
            "limitations": ["仅评测单一环境"],
            "practical_value": "适合工具型 Agent 设计",
            "research_details": {
                "agent_environment": "browser benchmark",
                "agent_mechanism": "planner with episodic memory",
                "key_benchmarks": ["BrowserGym"],
            },
        }

    monkeypatch.setenv("DEEPSEEK_API_KEY", "secret")
    monkeypatch.setattr(ChatCompletionClient, "summarize", fake_summarize)
    monkeypatch.setattr(ChatCompletionClient, "analyze_for_site", fake_analyze)
    monkeypatch.setattr(
        "daily_paper.summarizer.extract_full_text_for_analysis",
        lambda *args, **kwargs: "full paper text",
    )

    analyze_papers_for_site([paper], make_summary_config())

    assert paper.research_details["agent_environment"] == "browser benchmark"
    assert paper.research_details["key_benchmarks"] == ["BrowserGym"]
    assert paper.ab_test == "unknown"
    assert paper.ab_test_evidence == ""
