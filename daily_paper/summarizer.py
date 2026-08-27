import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List

from .config import SummaryConfig, TrackConfig
from .filtering import ALLOWED_TAGS, MAX_TAGS, infer_tags, normalize_tag
from .fulltext import extract_full_text_for_analysis
from .models import Paper
from .tracks import (
    TOPIC_TERMS,
    TrackMatch,
    apply_track_match,
    apply_track_score,
    classify_deterministically,
)

ANALYSIS_PROMPT_VERSION = "site-analysis-v3-tracks"
PREFERENCE_PROMPT_VERSION = "preference-score-v1"
SITE_ANALYSIS_FIELDS = [
    "generated_summary",
    "core_method",
    "innovation_points",
    "experiment_results",
    "ab_test",
    "ab_test_evidence",
    "limitations",
    "practical_value",
    "analysis_basis",
    "analysis_status",
    "analysis_signature",
    "tags",
    "llm_score",
    "llm_score_rationale",
    "preference_signals",
    "research_details",
]
TAG_PROMPT = ", ".join(ALLOWED_TAGS)
RESEARCH_DETAIL_KEYS = (
    "training_objective",
    "feedback_source",
    "model_data_scale",
    "key_benchmarks",
    "artifacts",
    "agent_environment",
    "agent_mechanism",
    "interaction_horizon",
    "agent_evaluation",
)


def summarize_papers(papers: List[Paper], config: SummaryConfig) -> List[Paper]:
    api_key = _api_key_for_provider(config.provider)
    if not api_key:
        for paper in papers:
            paper.generated_summary = fallback_summary(paper.abstract, config.max_sentences)
            if not paper.tags:
                paper.tags = infer_tags(paper)
        return papers

    def summarize_one(paper: Paper) -> Dict[str, object]:
        client = ChatCompletionClient(
            api_key=api_key,
            base_url=config.base_url,
            model=config.model,
            provider=config.provider,
        )
        try:
            return client.summarize(paper, language=config.language)
        except Exception as exc:
            print(
                "Warning: LLM summary failed for %s; using abstract fallback. %s"
                % (paper.id, exc),
                file=sys.stderr,
            )
            return {}

    workers = max(1, int(config.summary_workers))
    if workers == 1 or len(papers) <= 1:
        for paper in papers:
            _apply_summary_result(paper, summarize_one(paper), config)
        return papers

    with ThreadPoolExecutor(max_workers=min(workers, len(papers))) as executor:
        futures = {executor.submit(summarize_one, paper): paper for paper in papers}
        for future in as_completed(futures):
            paper = futures[future]
            try:
                result = future.result()
            except Exception as exc:
                print(
                    "Warning: LLM summary failed for %s; using abstract fallback. %s"
                    % (paper.id, exc),
                    file=sys.stderr,
                )
                result = {}
            _apply_summary_result(paper, result, config)
    return papers


def score_papers_with_llm(papers: List[Paper], config: SummaryConfig) -> List[Paper]:
    if not papers:
        return papers
    api_key = _api_key_for_provider(config.provider)
    if not api_key:
        for paper in papers:
            _apply_preference_score_result(paper, fallback_preference_score(paper))
        return papers

    def score_one(paper: Paper) -> Dict[str, object]:
        client = ChatCompletionClient(
            api_key=api_key,
            base_url=config.base_url,
            model=config.analysis_model,
            provider=config.provider,
        )
        try:
            return client.score_preference(paper, language=config.language)
        except Exception as exc:
            print(
                "Warning: LLM preference scoring failed for %s; using rule fallback. %s"
                % (paper.id, exc),
                file=sys.stderr,
            )
            return fallback_preference_score(paper)

    workers = max(1, int(config.analysis_workers))
    if workers == 1 or len(papers) <= 1:
        for paper in papers:
            _apply_preference_score_result(paper, score_one(paper))
        return papers

    with ThreadPoolExecutor(max_workers=min(workers, len(papers))) as executor:
        futures = {executor.submit(score_one, paper): paper for paper in papers}
        for future in as_completed(futures):
            paper = futures[future]
            try:
                result = future.result()
            except Exception as exc:
                print(
                    "Warning: LLM preference scoring failed for %s; using rule fallback. %s"
                    % (paper.id, exc),
                    file=sys.stderr,
                )
                result = fallback_preference_score(paper)
            _apply_preference_score_result(paper, result)
    return papers


def classify_and_score_track(
    papers: List[Paper], track: TrackConfig, config: SummaryConfig
) -> List[Paper]:
    if not papers:
        return papers
    if track.key == "generative_rec":
        accepted = []
        for paper in papers:
            match = classify_deterministically(paper, track)
            if apply_track_match(paper, match, track.relevance_threshold):
                accepted.append(paper)
        score_papers_with_llm(accepted, config)
        for paper in accepted:
            paper.track_scores[track.key] = paper.llm_score
            paper.track_score_rationales[track.key] = paper.llm_score_rationale
        return papers

    api_key = _api_key_for_provider(config.provider)

    def score_one(paper: Paper) -> Dict[str, object]:
        if not api_key:
            return _fallback_track_result(paper, track)
        client = ChatCompletionClient(
            api_key=api_key,
            base_url=config.base_url,
            model=config.analysis_model,
            provider=config.provider,
        )
        try:
            return client.classify_and_score_track(
                paper, track.key, language=config.language
            )
        except Exception as exc:
            print(
                "Warning: track scoring failed for %s; using rule fallback. %s"
                % (paper.id, exc),
                file=sys.stderr,
            )
            return _fallback_track_result(paper, track)

    workers = max(1, int(config.analysis_workers))
    if workers == 1 or len(papers) <= 1:
        for paper in papers:
            _apply_track_scoring_result(paper, track, score_one(paper))
        return papers

    with ThreadPoolExecutor(max_workers=min(workers, len(papers))) as executor:
        futures = {executor.submit(score_one, paper): paper for paper in papers}
        for future in as_completed(futures):
            paper = futures[future]
            try:
                result = future.result()
            except Exception:
                result = _fallback_track_result(paper, track)
            _apply_track_scoring_result(paper, track, result)
    return papers


def _fallback_track_result(paper: Paper, track: TrackConfig) -> Dict[str, object]:
    match = classify_deterministically(paper, track)
    text = " ".join([paper.title, paper.abstract, paper.abs_url]).lower()
    return {
        "track_relevance": match.relevance,
        "topics": match.topics,
        "primary_topic": match.primary_topic,
        "evidence_text": match.evidence,
        "score_breakdown": {
            "relevance": round(match.relevance * 0.30),
            "technical": min(25, 10 + max(0, len(match.topics) - 1) * 3),
            "evidence": 10 if paper.abstract else 3,
            "novelty": 5,
            "reproducibility": 5 if "github" in text or "code" in text else 0,
        },
        "rationale": match.evidence,
        "research_details": {},
    }


def _apply_track_scoring_result(
    paper: Paper, track: TrackConfig, result: Dict[str, object]
) -> None:
    allowed_topics = set(TOPIC_TERMS)
    topics = [
        str(value)
        for value in (result.get("topics") or [])
        if str(value) in allowed_topics
    ]
    primary_topic = str(result.get("primary_topic", ""))
    if primary_topic not in topics:
        primary_topic = topics[0] if topics else ""
    relevance = max(0, min(100, _safe_int(result.get("track_relevance"))))
    match = TrackMatch(
        track=track.key,
        relevance=relevance,
        topics=topics,
        primary_topic=primary_topic,
        evidence=str(result.get("evidence_text", "")).strip(),
    )
    if not apply_track_match(paper, match, track.relevance_threshold):
        return
    apply_track_score(
        paper,
        track.key,
        result.get("score_breakdown") or {},
        str(result.get("rationale", "")),
    )
    paper.research_details.update(
        _clean_research_details(result.get("research_details") or {})
    )


def _apply_summary_result(paper: Paper, result: Dict[str, object], config: SummaryConfig) -> None:
    paper.generated_summary = result.get("summary") or fallback_summary(
        paper.abstract, config.max_sentences
    )
    tags = result.get("tags") or []
    paper.tags = _clean_tags(tags) or paper.tags or infer_tags(paper)


def _apply_preference_score_result(paper: Paper, result: Dict[str, object]) -> None:
    score = _safe_int(result.get("score"), default=0)
    paper.llm_score = max(0, min(100, score))
    reasons = _clean_list(result.get("reasons"), fallback=[], limit=3)
    signals = _clean_list(result.get("signals"), fallback=[], limit=5)
    paper.preference_signals = signals
    paper.llm_score_rationale = "；".join(reasons)
    paper.score += paper.llm_score


def fallback_preference_score(paper: Paper) -> Dict[str, object]:
    text = " ".join(
        [
            paper.title,
            paper.abstract,
            paper.venue,
            paper.venue_key,
            " ".join(paper.categories),
            " ".join(paper.affiliations),
        ]
    ).lower()
    score = 0
    reasons = []
    signals = []
    if paper.ab_test == "yes" or any(
        term in text
        for term in (
            "online a/b",
            "online ab",
            "a/b test",
            "online experiment",
            "live traffic",
            "production experiment",
            "bucket test",
        )
    ):
        score += 45
        signals.append("Online A/B")
        reasons.append("明确或疑似包含线上 A/B/生产流量实验信号。")
    if _is_top_venue_metadata(paper):
        score += 25
        signals.append("Top venue")
        reasons.append("论文来自重点会议或会议来源。")
    if any(
        term in text
        for term in (
            "generative recommendation",
            "generative recommender",
            "generative retrieval",
            "semantic id",
            "semantic ids",
            "semantic identifier",
            "llm4rec",
        )
    ):
        score += 20
        signals.append("Generative Rec / Semantic ID")
        reasons.append("主题与生成式推荐、LLM4Rec 或语义 ID 强相关。")
    if _has_known_internet_company_metadata(paper):
        score += 10
        signals.append("Industry company")
        reasons.append("作者单位包含知名互联网公司。")
    return {"score": min(score, 100), "reasons": reasons, "signals": signals}


def analyze_papers_for_site(papers: List[Paper], config: SummaryConfig) -> List[Paper]:
    summarize_papers(papers, config)
    api_key = _api_key_for_provider(config.provider)
    if not api_key:
        for paper in papers:
            _apply_analysis_result(paper, {})
            paper.analysis_signature = expected_analysis_signature(paper, config)
        return papers
    def analyze_one(paper: Paper) -> Dict[str, object]:
        client = ChatCompletionClient(
            api_key=api_key,
            base_url=config.base_url,
            model=config.analysis_model,
            provider=config.provider,
        )
        full_text = extract_full_text_for_analysis(
            paper,
            max_chars=config.full_text_max_chars,
            timeout_seconds=config.full_text_timeout_seconds,
        )
        paper.analysis_basis = "full_text" if full_text else "metadata"
        try:
            return client.analyze_for_site(paper, full_text=full_text, language=config.language)
        except Exception as exc:
            print(
                "Warning: site analysis failed for %s; using conservative fallback. %s"
                % (paper.id, exc),
                file=sys.stderr,
            )
            return {}

    workers = max(1, int(config.analysis_workers))
    if workers == 1 or len(papers) <= 1:
        for paper in papers:
            _apply_analysis_result(paper, analyze_one(paper))
            paper.analysis_signature = expected_analysis_signature(paper, config)
        return papers

    with ThreadPoolExecutor(max_workers=min(workers, len(papers))) as executor:
        futures = {executor.submit(analyze_one, paper): paper for paper in papers}
        for future in as_completed(futures):
            paper = futures[future]
            try:
                result = future.result()
            except Exception as exc:
                print(
                    "Warning: site analysis failed for %s; using conservative fallback. %s"
                    % (paper.id, exc),
                    file=sys.stderr,
                )
                result = {}
            _apply_analysis_result(paper, result)
            paper.analysis_signature = expected_analysis_signature(paper, config)
    return papers


def fallback_summary(text: str, max_sentences: int = 3) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        return "No abstract is available."
    sentences = re.split(r"(?<=[.!?])\s+", cleaned)
    summary = " ".join(sentences[:max_sentences]).strip()
    return summary if len(summary) <= 700 else summary[:697].rstrip() + "..."


def _apply_analysis_result(paper: Paper, result: Dict[str, object]) -> None:
    paper.analysis_status = "complete" if result else "fallback"
    if result.get("summary"):
        paper.generated_summary = str(result.get("summary")).strip()
    paper.core_method = str(
        result.get("core_method") or "需要全文或补充材料进一步确认核心方法。"
    ).strip()
    paper.innovation_points = _clean_list(
        result.get("innovation_points"),
        fallback=[
            "全文信息不足，暂未识别出明确创新点。"
            if not paper.abstract
            else "未能从全文/元数据中稳定抽取明确创新点。"
        ],
        limit=3,
    )
    paper.experiment_results = _clean_list(
        result.get("experiment_results"),
        fallback=["全文未提供足够实验结果细节，或解析失败。"],
        limit=3,
    )
    llm_only = "llm_systems" in paper.tracks and "generative_rec" not in paper.tracks
    if llm_only:
        paper.ab_test = "unknown"
        paper.ab_test_evidence = ""
    else:
        ab_test = str(result.get("ab_test", "unknown")).lower().strip()
        paper.ab_test = ab_test if ab_test in ("yes", "no", "unknown") else "unknown"
        original_ab_test = paper.ab_test
        if paper.ab_test == "unknown":
            paper.ab_test = "no"
        if original_ab_test == "unknown":
            paper.ab_test_evidence = "论文未报告线上 A/B 测试。"
        else:
            paper.ab_test_evidence = str(
                result.get("ab_test_evidence")
                or (
                    "论文全文未报告线上 A/B 测试。"
                    if paper.analysis_basis == "full_text"
                    else "论文未报告线上 A/B 测试。"
                )
            ).strip()
    paper.limitations = _clean_list(
        result.get("limitations"),
        fallback=["需要阅读全文确认实验设置、数据集和适用边界。"],
        limit=2,
    )
    paper.practical_value = str(
        result.get("practical_value")
        or (
            "可作为大模型后训练或 Agent 方向的跟进阅读。"
            if llm_only
            else "可作为推荐系统相关方向的跟进阅读。"
        )
    ).strip()
    paper.research_details.update(
        _clean_research_details(result.get("research_details") or {})
    )
    paper.tags = _clean_tags(result.get("tags") or paper.tags) or paper.tags or infer_tags(paper)


def expected_analysis_signature(paper: Paper, config: SummaryConfig) -> str:
    payload = {
        "prompt_version": ANALYSIS_PROMPT_VERSION,
        "provider": config.provider,
        "summary_model": config.model,
        "analysis_model": config.analysis_model,
        "language": config.language,
        "full_text_max_chars": config.full_text_max_chars,
        "paper": {
            "id": paper.id,
            "title": paper.title,
            "updated": paper.updated,
            "abstract": paper.abstract,
            "categories": paper.categories,
            "source": paper.source,
            "venue": paper.venue,
            "tracks": paper.tracks,
            "topics": paper.topics,
        },
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def has_reusable_site_analysis(
    paper: Paper, config: SummaryConfig, expected_signature: str = None
) -> bool:
    if paper.analysis_signature != (expected_signature or expected_analysis_signature(paper, config)):
        return False
    if paper.analysis_status not in ("complete", "cached"):
        return False
    return has_complete_site_analysis_fields(paper)


def has_legacy_site_analysis(paper: Paper) -> bool:
    if paper.analysis_signature:
        return False
    if paper.analysis_status not in ("", "complete", "cached"):
        return False
    return has_complete_site_analysis_fields(paper)


def has_complete_site_analysis_fields(paper: Paper) -> bool:
    required = [
        paper.generated_summary,
        paper.core_method,
        paper.innovation_points,
        paper.experiment_results,
        paper.limitations,
        paper.practical_value,
    ]
    return all(bool(value) for value in required)


def copy_site_analysis(source: Paper, target: Paper) -> None:
    for field_name in SITE_ANALYSIS_FIELDS:
        value = getattr(source, field_name)
        if isinstance(value, list):
            value = list(value)
        elif isinstance(value, dict):
            value = dict(value)
        setattr(target, field_name, value)
    target.analysis_status = "cached"


def _clean_list(values, fallback: List[str], limit: int) -> List[str]:
    if isinstance(values, str):
        values = [values]
    cleaned = []
    for value in values or []:
        text = str(value).strip()
        if text and text not in cleaned:
            cleaned.append(text)
        if len(cleaned) >= limit:
            break
    return cleaned or fallback


def _clean_research_details(values) -> Dict[str, object]:
    if not isinstance(values, dict):
        return {}
    cleaned = {}
    for key in RESEARCH_DETAIL_KEYS:
        value = values.get(key)
        if isinstance(value, list):
            items = _clean_list(value, fallback=[], limit=8)
            if items:
                cleaned[key] = items
        elif value is not None:
            text = str(value).strip()
            if text:
                cleaned[key] = text
    return cleaned


class ChatCompletionClient:
    def __init__(self, api_key: str, base_url: str, model: str, provider: str = "deepseek"):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.provider = provider

    def summarize(self, paper: Paper, language: str = "zh") -> Dict[str, object]:
        user_prompt = (
            "Title: %s\nAuthors: %s\nVenue: %s\nSource: %s\nCategories: %s\nAbstract: %s"
            % (
                paper.title,
                ", ".join(paper.authors),
                paper.venue,
                paper.source,
                ", ".join(paper.categories),
                paper.abstract or "No abstract is available. Summarize cautiously from title and venue only.",
            )
        )
        system_prompt = (
            "请面向推荐系统研究者总结论文。输出严格 JSON："
            '{"summary": "不超过三句中文摘要", "tags": ["从给定集合中选择2到4个标签"]}。'
            "标签集合：%s。优先选择细粒度主题标签；只有没有更具体标签时才使用 General Rec。"
            "不要输出 JSON 以外的文字。"
            % TAG_PROMPT
        )
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
            "thinking": {"type": "disabled"},
            "max_tokens": 500,
        }
        if self.provider.lower() != "deepseek":
            payload.pop("thinking", None)
        request = urllib.request.Request(
            self.base_url + "/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": "Bearer %s" % self.api_key,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise RuntimeError(_format_http_error(exc)) from exc
        output = _extract_chat_output_text(data)
        return json.loads(output)

    def analyze_for_site(self, paper: Paper, full_text: str = "", language: str = "zh") -> Dict[str, object]:
        evidence_label = "FULL_TEXT" if full_text else "METADATA_ONLY"
        user_prompt = (
            "Title: %s\nAuthors: %s\nVenue: %s\nSource: %s\nPublished: %s\n"
            "Categories: %s\nEvidence basis: %s\nAbstract: %s\nExisting summary: %s\nFull text excerpt: %s"
            % (
                paper.title,
                ", ".join(paper.authors),
                paper.venue,
                paper.source,
                paper.published_date,
                ", ".join(paper.categories),
                evidence_label,
                paper.abstract or "No abstract is available.",
                paper.generated_summary,
                full_text or "No full text excerpt is available.",
            )
        )
        system_prompt = (
            "你是推荐系统方向的论文分析助手。请优先基于 Full text excerpt 理解论文；"
            "只有在没有全文时才基于 title/abstract/venue/source 谨慎分析。"
            "为 GitHub Pages 论文卡片输出严格 JSON，不要输出 JSON 之外的文字。"
            "如果没有证据，不要猜测。线上 A/B 测试只能在全文或摘要明确提到 online A/B test、"
            "production experiment、live traffic、online experiment、bucket test 等证据时标记 yes；"
            "如果全文存在但没有报告线上 A/B 测试，ab_test 必须为 no，ab_test_evidence 写“论文全文未报告线上 A/B 测试”。"
            "如果没有全文且元数据也没有证据，ab_test 为 unknown。"
            "JSON schema: {"
            "\"summary\": \"三句以内中文摘要\", "
            "\"core_method\": \"一句中文概括核心方法\", "
            "\"innovation_points\": [\"1-3条中文创新点\"], "
            "\"experiment_results\": [\"1-3条中文实验结果或评测结论；无证据则说明全文未提供\"], "
            "\"ab_test\": \"yes|no|unknown\", "
            "\"ab_test_evidence\": \"中文证据说明；全文无证据写论文全文未报告线上 A/B 测试\", "
            "\"limitations\": [\"1-2条局限或不确定性\"], "
            "\"practical_value\": \"一句中文说明对推荐系统实践的价值\", "
            "\"tags\": [\"从集合中选择2到5个标签\"]"
            "}。标签集合：%s。优先选择细粒度主题标签；只有没有更具体标签时才使用 General Rec。"
            % TAG_PROMPT
        )
        if "llm_systems" in paper.tracks and "generative_rec" not in paper.tracks:
            system_prompt = (
                "你是大模型后训练、强化学习与 Agent 方向的论文分析助手。"
                "优先依据全文，证据不足时明确说明，不要猜测。输出严格 JSON，"
                "包含 summary、core_method、innovation_points、experiment_results、limitations、"
                "practical_value、tags 和 research_details。research_details 只允许这些键："
                "training_objective、feedback_source、model_data_scale、key_benchmarks、artifacts、"
                "agent_environment、agent_mechanism、interaction_horizon、agent_evaluation。"
                "列表型信息使用 JSON 数组，其余使用字符串；没有证据的键不要输出。"
            )
        payload = self._build_payload(system_prompt=system_prompt, user_prompt=user_prompt, max_tokens=1000)
        data = self._post_chat(payload)
        output = _extract_chat_output_text(data)
        return json.loads(output)

    def classify_and_score_track(
        self, paper: Paper, track_key: str, language: str = "zh"
    ) -> Dict[str, object]:
        user_prompt = (
            "Title: %s\nAuthors: %s\nVenue: %s\nPublished: %s\nCategories: %s\nAbstract: %s"
            % (
                paper.title,
                ", ".join(paper.authors),
                paper.venue,
                paper.published_date,
                ", ".join(paper.categories),
                paper.abstract or "No abstract is available.",
            )
        )
        system_prompt = (
            "Classify and rank a paper for the llm_systems research track. "
            "Allowed topics are post_training, llm_rl, and llm_agent. "
            "Exclude traditional robotics, control, and general RL without a material language-model contribution. "
            "Return strict JSON with track_relevance 0-100, topics, primary_topic, evidence_text, "
            "score_breakdown, rationale, and research_details. Score dimensions are: "
            "relevance 0-30, technical 0-25, evidence 0-20, novelty 0-15, reproducibility 0-10. "
            "research_details may contain training_objective, feedback_source, model_data_scale, "
            "key_benchmarks, artifacts, agent_environment, agent_mechanism, interaction_horizon, "
            "and agent_evaluation. Do not infer facts absent from the metadata."
        )
        payload = self._build_payload(
            system_prompt=system_prompt, user_prompt=user_prompt, max_tokens=800
        )
        data = self._post_chat(payload)
        return json.loads(_extract_chat_output_text(data))

    def score_preference(self, paper: Paper, language: str = "zh") -> Dict[str, object]:
        user_prompt = (
            "Title: %s\nAuthors: %s\nAffiliations: %s\nVenue: %s\nVenue key: %s\n"
            "Source: %s\nStatus: %s\nPublished: %s\nCategories: %s\nAbstract: %s"
            % (
                paper.title,
                ", ".join(paper.authors),
                "; ".join(paper.display_affiliations),
                paper.venue,
                paper.venue_key,
                paper.source,
                paper.status,
                paper.published_date,
                ", ".join(paper.categories),
                paper.abstract or "No abstract is available.",
            )
        )
        system_prompt = (
            "你是推荐系统论文检索的排序助手。请只基于给定 metadata 打分，不要臆测。"
            "输出严格 JSON，不要输出 JSON 之外的文字。"
            "打分范围 0-100，表示这篇论文对“生成式推荐/语义 ID/工业推荐实践”读者的优先级。"
            "权重偏好：1) 明确有线上 A/B、online experiment、live traffic、production/bucket experiment 证据权重最高；"
            "2) RecSys、SIGIR、WWW、KDD、WSDM、CIKM、ICLR、AAAI、ICML、NeurIPS 等顶会已发表次之；"
            "3) 与 generative recommendation、generative retrieval、semantic ID/identifier、LLM4Rec 强相关加高分；"
            "4) 作者单位含 Google/DeepMind、Meta、Amazon、Microsoft、Netflix、Spotify、LinkedIn、ByteDance/TikTok、Alibaba、Tencent、Baidu、Kuaishou、Meituan、JD、Pinterest、Airbnb、Uber 等知名互联网公司加分。"
            "如果只有离线实验，不要给线上 A/B 信号。"
            "JSON schema: {\"score\": 0-100, \"signals\": [\"Online A/B|Top venue|Generative Rec / Semantic ID|Industry company\"], \"reasons\": [\"1-3条中文依据\"]}。"
        )
        payload = self._build_payload(system_prompt=system_prompt, user_prompt=user_prompt, max_tokens=500)
        data = self._post_chat(payload)
        output = _extract_chat_output_text(data)
        return json.loads(output)

    def _build_payload(self, system_prompt: str, user_prompt: str, max_tokens: int) -> Dict[str, object]:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
            "thinking": {"type": "disabled"},
            "max_tokens": max_tokens,
        }
        if self.provider.lower() != "deepseek":
            payload.pop("thinking", None)
        return payload

    def _post_chat(self, payload: Dict[str, object]) -> Dict[str, object]:
        request = urllib.request.Request(
            self.base_url + "/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": "Bearer %s" % self.api_key,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise RuntimeError(_format_http_error(exc)) from exc


def _api_key_for_provider(provider: str) -> str:
    if provider.lower() == "deepseek":
        return os.getenv("DEEPSEEK_API_KEY", "")
    return os.getenv("LLM_API_KEY", "")


def _extract_chat_output_text(data: Dict[str, object]) -> str:
    choices = data.get("choices", []) or []
    if not choices:
        return ""
    message = choices[0].get("message", {}) or {}
    content = message.get("content", "")
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or ""))
            else:
                parts.append(str(item))
        return "\n".join(parts).strip()
    return str(content).strip()


def _format_http_error(exc: urllib.error.HTTPError) -> str:
    try:
        payload = json.loads(exc.read().decode("utf-8"))
        message = payload.get("error", {}).get("message")
    except Exception:
        message = ""
    if message:
        return "LLM API error %s: %s" % (exc.code, message)
    return "LLM API error %s" % exc.code


def _clean_tags(tags) -> List[str]:
    allowed = set(ALLOWED_TAGS)
    cleaned = []
    for tag in tags:
        value = normalize_tag(tag)
        if value in allowed and value not in cleaned:
            cleaned.append(value)
    if len(cleaned) > 1 and "General Rec" in cleaned:
        cleaned.remove("General Rec")
    return cleaned[:MAX_TAGS]


def _safe_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _is_top_venue_metadata(paper: Paper) -> bool:
    top_venues = {
        "recsys",
        "sigir",
        "www",
        "kdd",
        "wsdm",
        "cikm",
        "iclr",
        "aaai",
        "icml",
        "neurips",
    }
    values = [paper.venue_key, paper.venue, paper.primary_category] + list(paper.categories)
    return any(str(value).strip().lower() in top_venues for value in values)


def _has_known_internet_company_metadata(paper: Paper) -> bool:
    text = " ".join(paper.affiliations).lower()
    companies = [
        "google",
        "deepmind",
        "meta",
        "facebook",
        "amazon",
        "microsoft",
        "netflix",
        "spotify",
        "linkedin",
        "bytedance",
        "tiktok",
        "alibaba",
        "ant group",
        "tencent",
        "baidu",
        "kuaishou",
        "meituan",
        "jd.com",
        "pinterest",
        "airbnb",
        "uber",
    ]
    return any(company in text for company in companies)
