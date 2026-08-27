from dataclasses import dataclass
import re
from typing import Dict, List

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
