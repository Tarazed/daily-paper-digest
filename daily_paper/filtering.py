import datetime as _dt
import re
from typing import Dict, Iterable, List

from .config import ArxivConfig
from .models import Paper

HIGH_PRIORITY_TERMS = [
    "llm4rec",
    "agent4rec",
    "generative recommendation",
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

TAG_RULES = [
    ("LLM4Rec", ["llm4rec", "large language model", "llm-based recommendation"]),
    ("Agent4Rec", ["agent4rec", "agent recommendation", "recommendation agent"]),
    ("Generative Rec", ["generative recommendation", "generative recommender"]),
    ("Sequential Rec", ["sequential recommendation", "next item recommendation"]),
    ("Conversational Rec", ["conversational recommendation", "dialogue recommendation"]),
    ("RecSys", ["recommender system", "recommendation"]),
    ("Evaluation", ["evaluation", "evaluate", "metric"]),
    ("Dataset", ["dataset", "benchmark data"]),
    ("Benchmark", ["benchmark", "leaderboard"]),
]


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
    if paper.source == "DBLP" and not paper.abstract:
        score -= 8
    return score


def infer_tags(paper: Paper) -> List[str]:
    text = _search_text(paper)
    tags = []
    for tag, terms in TAG_RULES:
        if any(term in text for term in terms):
            tags.append(tag)
    return tags or ["RecSys"]


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
    value = " ".join([paper.title, paper.abstract, " ".join(paper.categories)])
    return re.sub(r"\s+", " ", value).lower()
