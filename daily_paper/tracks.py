from dataclasses import dataclass
import datetime as _dt
import re
from typing import Dict, Iterable, List

from .config import TrackConfig
from .models import Paper


TOPIC_TERMS = {
    "post_training": (
        "post training",
        "supervised fine tuning",
        "sft",
        "instruction tuning",
        "direct preference optimization",
        "dpo",
        "ipo",
        "kto",
        "preference optimization",
        "reward model",
        "process reward",
        "distillation",
        "self improvement",
        "self training",
    ),
    "llm_rl": (
        "rlhf",
        "rlaif",
        "ppo",
        "grpo",
        "reinforcement learning for reasoning",
        "reinforcement learning of language model",
        "verifiable reward",
        "credit assignment",
        "reward hacking",
        "sparse reward",
        "agent reinforcement learning",
    ),
    "llm_agent": (
        "language model agent",
        "language model agents",
        "llm agent",
        "tool use",
        "tool agent",
        "call tools",
        "function calling",
        "agent memory",
        "episodic memory",
        "multi agent",
        "computer use",
        "planning agent",
        "agent evaluation",
        "agent benchmark",
    ),
}
TOPIC_PRIORITY = ("llm_rl", "post_training", "llm_agent")
LLM_CONTEXT = (
    "language model",
    "language models",
    "llm",
    "foundation model",
    "reasoning model",
    "transformer",
)
HARD_EXCLUDES = (
    "robot control",
    "robotic manipulation",
    "robot manipulation",
    "locomotion",
    "autonomous driving",
    "power grid control",
)
EXPLICIT_AGENT_CONTEXT = ("language model agent", "language model agents", "llm agent")
LLM_SCORE_LIMITS = {
    "relevance": 30,
    "technical": 25,
    "evidence": 20,
    "novelty": 15,
    "reproducibility": 10,
}


@dataclass(frozen=True)
class TrackMatch:
    track: str
    relevance: int
    topics: List[str]
    primary_topic: str
    evidence: str


def classify_deterministically(paper: Paper, track: TrackConfig) -> TrackMatch:
    text = _paper_text(paper)
    if track.key != "llm_systems":
        return _classify_keyword_track(text, track)

    explicit_agent = _matching_terms(text, EXPLICIT_AGENT_CONTEXT)
    excluded = _matching_terms(text, HARD_EXCLUDES)
    if excluded and not explicit_agent:
        return TrackMatch(track.key, 0, [], "", "Excluded: %s" % ", ".join(excluded))

    llm_context = _matching_terms(text, LLM_CONTEXT)
    if not llm_context:
        return TrackMatch(track.key, 0, [], "", "No explicit language-model context.")

    matches: Dict[str, List[str]] = {
        topic: _matching_terms(text, terms) for topic, terms in TOPIC_TERMS.items()
    }
    topics = [topic for topic in TOPIC_TERMS if matches[topic]]
    if not topics:
        return TrackMatch(track.key, 0, [], "", "No configured LLM research topic matched.")

    primary_topic = max(
        topics,
        key=lambda topic: (len(matches[topic]), -TOPIC_PRIORITY.index(topic)),
    )
    evidence_terms = []
    for topic in topics:
        evidence_terms.extend(matches[topic])
    relevance = min(95, 70 + 5 * max(0, len(dict.fromkeys(evidence_terms)) - 1))
    evidence = "Matched %s with LLM context %s." % (
        ", ".join(dict.fromkeys(evidence_terms)),
        ", ".join(llm_context),
    )
    return TrackMatch(track.key, relevance, topics, primary_topic, evidence)


def apply_track_match(paper: Paper, match: TrackMatch, threshold: int) -> bool:
    current_primary_relevance = paper.track_relevance.get(paper.primary_track, -1)
    paper.track_relevance[match.track] = max(0, min(100, int(match.relevance)))
    paper.track_relevance_evidence[match.track] = str(match.evidence).strip()
    if match.relevance < threshold:
        return False

    if match.track not in paper.tracks:
        paper.tracks.append(match.track)
    for topic in match.topics:
        if topic not in paper.topics:
            paper.topics.append(topic)
    if not paper.primary_track or match.relevance > current_primary_relevance:
        paper.primary_track = match.track
        paper.primary_topic = match.primary_topic
    elif paper.primary_track == match.track and not paper.primary_topic:
        paper.primary_topic = match.primary_topic
    return True


def apply_track_score(
    paper: Paper,
    track_key: str,
    breakdown: Dict[str, int],
    rationale: str,
) -> int:
    cleaned = {
        key: max(0, min(limit, _safe_int((breakdown or {}).get(key, 0))))
        for key, limit in LLM_SCORE_LIMITS.items()
    }
    score = sum(cleaned.values())
    paper.track_score_breakdowns[track_key] = cleaned
    paper.track_scores[track_key] = score
    paper.track_score_rationales[track_key] = str(rationale or "").strip()
    return score


def select_track_digest(
    papers: Iterable[Paper],
    track_key: str,
    quota: int,
    topic_quotas: Dict[str, int],
    sent_ids=(),
    relevance_threshold: int = 70,
) -> List[Paper]:
    sent = set(sent_ids or ())
    eligible_by_id = {}
    for paper in papers:
        if paper.id in sent or track_key not in paper.tracks:
            continue
        if paper.track_relevance.get(track_key, 0) < relevance_threshold:
            continue
        current = eligible_by_id.get(paper.id)
        if current is None or _track_sort_key(paper, track_key) < _track_sort_key(
            current, track_key
        ):
            eligible_by_id[paper.id] = paper

    ordered = sorted(
        eligible_by_id.values(), key=lambda paper: _track_sort_key(paper, track_key)
    )
    selected = []
    selected_ids = set()
    for topic, reserved in (topic_quotas or {}).items():
        for paper in ordered:
            if len([item for item in selected if item.primary_topic == topic]) >= max(
                0, int(reserved)
            ):
                break
            if paper.id in selected_ids or paper.primary_topic != topic:
                continue
            selected.append(paper)
            selected_ids.add(paper.id)
            if len(selected) >= max(0, int(quota)):
                return selected

    for paper in ordered:
        if len(selected) >= max(0, int(quota)):
            break
        if paper.id in selected_ids:
            continue
        selected.append(paper)
        selected_ids.add(paper.id)
    return selected


def _classify_keyword_track(text: str, track: TrackConfig) -> TrackMatch:
    excluded = _matching_terms(text, tuple(track.arxiv.exclude_keywords))
    if excluded:
        return TrackMatch(track.key, 0, [], "", "Excluded: %s" % ", ".join(excluded))
    matches = _matching_terms(text, tuple(track.arxiv.include_keywords))
    if not matches:
        return TrackMatch(track.key, 0, [], "", "No configured track keyword matched.")
    relevance = min(95, 70 + 5 * max(0, len(matches) - 1))
    return TrackMatch(track.key, relevance, [], "", "Matched %s." % ", ".join(matches))


def _paper_text(paper: Paper) -> str:
    values = [paper.title, paper.abstract, paper.venue, " ".join(paper.categories)]
    return _normalize(" ".join(values))


def _matching_terms(text: str, terms) -> List[str]:
    matches = []
    for term in terms:
        normalized = _normalize(term)
        if normalized and " %s " % normalized in " %s " % text:
            matches.append(normalized)
    return list(dict.fromkeys(matches))


def _normalize(value: str) -> str:
    text = str(value or "").lower().replace("&", " and ")
    text = re.sub(r"[-_/]+", " ", text)
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _track_sort_key(paper: Paper, track_key: str):
    return (
        -paper.track_scores.get(track_key, 0),
        -_published_timestamp(paper.published),
        paper.title.lower(),
    )


def _published_timestamp(value: str) -> int:
    if not value:
        return 0
    for fmt, sample in (
        ("%Y-%m-%dT%H:%M:%S", value[:19]),
        ("%Y-%m-%d", value[:10]),
        ("%Y", value[:4]),
    ):
        try:
            return int(_dt.datetime.strptime(sample, fmt).timestamp())
        except ValueError:
            continue
    return 0


def _safe_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
