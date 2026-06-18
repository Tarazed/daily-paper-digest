import datetime as _dt
import re
from typing import Dict, Iterable, List

from .config import ArxivConfig
from .models import Paper

HIGH_PRIORITY_TERMS = [
    "llm4rec",
    "agent4rec",
    "generative recommendation",
    "generative recommender",
    "generative retrieval",
    "semantic id",
    "semantic ids",
    "semantic identifier",
    "semantic identifiers",
    "large language model recommendation",
    "large language models for recommendation",
    "agent recommendation",
    "recommendation agent",
]

MEDIUM_PRIORITY_TERMS = [
    "recommender system",
    "recommendation",
    "sequential recommendation",
    "conversational recommendation",
]

FALLBACK_TAG = "General Rec"
MAX_TAGS = 5

TAG_RULES = [
    (
        "LLM4Rec",
        [
            "llm4rec",
            "large language model recommendation",
            "large language models for recommendation",
            "large language model recommender",
            "llm recommendation",
            "llm recommender",
            "llm-based recommendation",
            "foundation model recommendation",
            "foundation model recommender",
        ],
    ),
    (
        "Semantic ID",
        [
            "semantic id",
            "semantic ids",
            "semantic identifier",
            "semantic identifiers",
            "hierarchical identifier",
            "hierarchical identifier recommendation",
        ],
    ),
    (
        "Item Tokenization",
        [
            "semantic token",
            "semantic tokens",
            "semantic tokenization",
            "item tokenization",
            "item identifier",
            "item identifiers",
            "discrete item token",
            "discrete token recommendation",
        ],
    ),
    (
        "Vector Quantization",
        [
            "vector quantization",
            "residual quantization",
            "rq-vae",
            "rqvae",
            "vq-vae",
            "vqvae",
            "codebook",
        ],
    ),
    (
        "Generative Rec",
        [
            "generative recommendation",
            "generative recommender",
            "generative recommender system",
            "generative sequential recommendation",
            "generative collaborative filtering",
            "autoregressive recommendation",
        ],
    ),
    ("Generative Retrieval", ["generative retrieval", "generative item retrieval"]),
    ("Generative Ranking", ["generative ranking"]),
    (
        "RAG Rec",
        [
            "rag recommendation",
            "rag recommender",
            "rag-based recommendation",
            "retrieval augmented recommendation",
            "retrieval-augmented recommendation",
            "retrieval augmented generation recommendation",
        ],
    ),
    (
        "Agent4Rec",
        [
            "agent4rec",
            "agent recommendation",
            "agent recommender",
            "agentic recommendation",
            "llm agent recommendation",
            "llm agent recommender",
            "recommendation agent",
            "recommender agent",
            "multi-agent recommendation",
            "multi-agent recommender",
            "tool-augmented recommendation",
            "planning recommendation agent",
            "reasoning recommendation agent",
        ],
    ),
    (
        "User Modeling",
        [
            "user modeling",
            "user modelling",
            "user preference modeling",
            "user preference modelling",
            "llm user modeling",
            "personalized llm recommendation",
            "user simulator recommendation",
            "llm user simulator",
        ],
    ),
    ("Sequential Rec", ["sequential recommendation", "next item recommendation"]),
    ("Conversational Rec", ["conversational recommendation", "dialogue recommendation"]),
    (
        "Online Eval",
        [
            "online a/b",
            "a/b test",
            "a/b testing",
            "online experiment",
            "production experiment",
            "live traffic",
            "bucket test",
        ],
    ),
    ("Benchmark", ["benchmark", "leaderboard"]),
    ("Dataset", ["dataset", "benchmark data", "corpus"]),
    ("Evaluation", ["evaluation", "evaluate", "evaluating", "metric", "metrics"]),
]

ALLOWED_TAGS = tuple([tag for tag, _terms in TAG_RULES] + [FALLBACK_TAG])
TAG_ALIASES = {
    "RecSys": FALLBACK_TAG,
    "General Recommendation": FALLBACK_TAG,
    "Recommendation": FALLBACK_TAG,
    "Generative Recommendation": "Generative Rec",
    "Sequential Recommendation": "Sequential Rec",
    "Conversational Recommendation": "Conversational Rec",
    "RAG Recommendation": "RAG Rec",
    "RAG RecSys": "RAG Rec",
    "Online A/B": "Online Eval",
    "Online Evaluation": "Online Eval",
}


def prepare_papers(
    papers: Iterable[Paper], config: ArxivConfig, state: Dict[str, Dict[str, str]]
) -> List[Paper]:
    filtered = []
    for paper in papers:
        if not _matches_interest(paper, config):
            continue
        apply_state(paper, state.get(paper.id, {}))
        paper.tags = infer_tags(paper)
        paper.score = score_paper(paper)
        filtered.append(paper)
    return sorted(filtered, key=_sort_key)


def apply_state(paper: Paper, values: Dict[str, str]) -> None:
    if not values:
        return
    paper.importance = str(values.get("importance", paper.importance))
    paper.read_status = str(values.get("read_status", paper.read_status))
    paper.notes = str(values.get("notes", paper.notes))


def score_paper(paper: Paper) -> int:
    text = _search_text(paper)
    score = 0
    for term in HIGH_PRIORITY_TERMS:
        if term in text:
            score += 10
    for term in MEDIUM_PRIORITY_TERMS:
        if term in text:
            score += 4
    if paper.importance == "high":
        score += 1000
    if "cs.IR" in paper.categories or paper.primary_category == "cs.IR":
        score += 2
    if paper.ab_test == "yes":
        score += 80
    if _is_top_venue(paper):
        score += 35
    if _has_known_internet_company(paper):
        score += 10
    if paper.source == "DBLP" and not paper.abstract:
        score -= 8
    return score


def sort_papers(papers: Iterable[Paper]) -> List[Paper]:
    return sorted(papers, key=_sort_key)


def infer_tags(paper: Paper) -> List[str]:
    text = _search_text(paper)
    tags = []
    for tag, terms in TAG_RULES:
        if any(term in text for term in terms):
            tags.append(tag)
    return tags[:MAX_TAGS] or [FALLBACK_TAG]


def normalize_tag(value) -> str:
    tag = str(value or "").strip()
    return TAG_ALIASES.get(tag, tag)


def _matches_interest(paper: Paper, config: ArxivConfig) -> bool:
    text = _search_text(paper)
    if any(term.lower() in text for term in config.exclude_keywords):
        return False
    return any(term.lower() in text for term in config.include_keywords)


def _sort_key(paper: Paper):
    return (-paper.score, -_sort_timestamp(paper.published), paper.title.lower())


def _sort_timestamp(value: str) -> int:
    if not value:
        return 0
    for fmt, sample in (("%Y-%m-%dT%H:%M:%S", value[:19]), ("%Y-%m-%d", value[:10]), ("%Y", value[:4])):
        try:
            return int(_dt.datetime.strptime(sample, fmt).timestamp())
        except ValueError:
            continue
    return 0


def _search_text(paper: Paper) -> str:
    value = " ".join(
        [
            paper.title,
            paper.abstract,
            paper.venue,
            paper.venue_key,
            paper.generated_summary,
            paper.core_method,
            paper.ab_test_evidence,
            paper.practical_value,
            " ".join(paper.categories),
            " ".join(paper.affiliations),
            " ".join(paper.innovation_points),
            " ".join(paper.experiment_results),
            " ".join(paper.preference_signals),
        ]
    )
    return re.sub(r"\s+", " ", value).lower()


def _is_top_venue(paper: Paper) -> bool:
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


def _has_known_internet_company(paper: Paper) -> bool:
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
