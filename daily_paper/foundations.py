import datetime as _dt
import re
from collections import Counter
from typing import Iterable, List

from .digest_state import DigestState
from .models import Paper


CITATION_VELOCITY_THRESHOLDS = (
    (16.0, 15),
    (8.0, 12),
    (4.0, 9),
    (2.0, 6),
    (1.0, 3),
)


def citation_velocity_points(paper: Paper, now=None) -> int:
    today = _as_date(now) or _dt.datetime.now(_dt.timezone.utc).date()
    published = _as_date(paper.published) or today
    age_days = max(0, (today - published).days)
    citations_per_month = max(0, paper.citation_count) / max(age_days / 30.0, 1.0)
    for threshold, points in CITATION_VELOCITY_THRESHOLDS:
        if citations_per_month >= threshold:
            return points
    return 0


def foundation_score(paper: Paper, now=None) -> int:
    track_key = "llm_systems" if "llm_systems" in paper.tracks else paper.primary_track
    breakdown = paper.track_score_breakdowns.get(track_key, {})
    relevance = round(max(0, min(100, paper.track_relevance.get(track_key, 0))) * 0.25)
    technical = max(0, min(25, _safe_int(breakdown.get("technical", 0))))
    evidence = round(max(0, min(20, _safe_int(breakdown.get("evidence", 0)))) * 0.75)
    reproducibility = max(0, min(10, _safe_int(breakdown.get("reproducibility", 0))))
    venue = 10 if _recognized_venue(paper) else 0
    return max(
        0,
        min(
            100,
            relevance
            + technical
            + evidence
            + citation_velocity_points(paper, now)
            + reproducibility
            + venue,
        ),
    )


def select_foundations(
    papers: Iterable[Paper], per_topic: int = 20, now=None, report=None
) -> List[Paper]:
    candidates = []
    seen = set()
    for paper in papers:
        if paper.id in seen or not paper.primary_topic:
            continue
        seen.add(paper.id)
        paper.foundation_score = foundation_score(paper, now)
        candidates.append(paper)

    selected = []
    relaxations = {}
    topics = ("post_training", "llm_rl", "llm_agent")
    extra_topics = sorted({paper.primary_topic for paper in candidates} - set(topics))
    for topic in topics + tuple(extra_topics):
        ordered = sorted(
            [paper for paper in candidates if paper.primary_topic == topic],
            key=lambda paper: (-paper.foundation_score, -paper.citation_count, paper.title.lower()),
        )
        topic_selected, topic_relaxations = _select_diverse(ordered, max(0, int(per_topic)))
        for paper in topic_selected:
            paper.foundation = True
        selected.extend(topic_selected)
        if topic_relaxations:
            relaxations[topic] = topic_relaxations
    if isinstance(report, dict):
        report["relaxations"] = relaxations
    return selected


def next_foundation_batch(
    papers: Iterable[Paper], state: DigestState, count: int = 3
) -> List[Paper]:
    by_id = {paper.id: paper for paper in papers}
    start = max(0, state.foundation_review_cursor)
    selected = []
    cursor = start
    while cursor < len(state.foundation_review_ids) and len(selected) < max(0, int(count)):
        paper_id = state.foundation_review_ids[cursor]
        cursor += 1
        paper = by_id.get(paper_id)
        if paper is not None:
            selected.append(paper)
    state.foundation_review_cursor = cursor
    return selected


def _select_diverse(papers: List[Paper], limit: int):
    selected = []
    selected_ids = set()
    series_counts = Counter()
    author_counts = Counter()
    month_counts = Counter()
    relaxations = []
    stages = (
        (4, 3, 6, None),
        (4, 3, None, "publication_month"),
        (4, None, None, "author_group"),
        (None, None, None, "method_series"),
    )
    for series_limit, author_limit, month_limit, relaxation in stages:
        before = len(selected)
        for paper in papers:
            if len(selected) >= limit:
                break
            if paper.id in selected_ids:
                continue
            series_key = _series_key(paper.title)
            author_key = _author_group_key(paper.authors)
            month_key = paper.published[:7]
            if series_limit is not None and series_counts[series_key] >= series_limit:
                continue
            if author_limit is not None and author_counts[author_key] >= author_limit:
                continue
            if month_limit is not None and month_counts[month_key] >= month_limit:
                continue
            selected.append(paper)
            selected_ids.add(paper.id)
            series_counts[series_key] += 1
            author_counts[author_key] += 1
            month_counts[month_key] += 1
        if relaxation and len(selected) > before:
            relaxations.append(relaxation)
        if len(selected) >= limit:
            break
    return selected, relaxations


def _series_key(title: str) -> str:
    text = str(title or "").lower()
    text = re.sub(r"\bv(?:ersion)?\s*\d+(?:\.\d+)*\b", " ", text)
    text = re.sub(r"\b(large|language|models?|llms?|for|with|using|via|towards?|a|an|the)\b", " ", text)
    tokens = re.findall(r"[a-z0-9]+", text)
    return " ".join(tokens[:4]) or "unknown"


def _author_group_key(authors) -> str:
    if not authors:
        return "unknown"
    return re.sub(r"[^a-z0-9]+", "", str(authors[0]).lower()) or "unknown"


def _recognized_venue(paper: Paper) -> bool:
    return bool(
        paper.venue_key
        or paper.venue
        or paper.status == "conference"
        or paper.source in ("DBLP", "OpenAlex", "Semantic Scholar")
    )


def _as_date(value):
    if isinstance(value, _dt.datetime):
        return value.date()
    if isinstance(value, _dt.date):
        return value
    text = str(value or "")[:10]
    try:
        return _dt.date.fromisoformat(text)
    except ValueError:
        return None


def _safe_int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
