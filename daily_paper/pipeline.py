import datetime as _dt
from dataclasses import asdict, dataclass, replace
import re
from typing import Dict, Iterable, List

from .arxiv import fetch_papers
from .config import AppConfig
from .dblp import fetch_dblp_papers
from .filtering import apply_state
from .models import Paper
from .summarizer import classify_and_score_track
from .tracks import select_track_digest


@dataclass
class TrackBuildResult:
    track_key: str
    papers: List[Paper]
    selected: List[Paper]
    source_errors: List[str]


def build_track(
    track_key: str,
    config: AppConfig,
    previous_papers: List[Paper],
    paper_state: Dict[str, Dict[str, str]],
    limit: int = None,
    days_back: int = None,
    fetch_arxiv=fetch_papers,
    fetch_conferences=fetch_dblp_papers,
) -> TrackBuildResult:
    if track_key not in config.tracks:
        raise ValueError("Unknown research track: %s" % track_key)
    track = config.tracks[track_key]
    arxiv_config = (
        replace(track.arxiv, days_back=int(days_back))
        if days_back is not None
        else track.arxiv
    )
    candidates = []
    source_errors = []
    for source_name, fetcher, source_config in (
        ("arXiv", fetch_arxiv, arxiv_config),
        ("conference", fetch_conferences, track.dblp),
    ):
        try:
            candidates.extend(fetcher(source_config))
        except Exception as exc:
            source_errors.append("%s: %s" % (source_name, exc))

    if not candidates and source_errors:
        cached = [paper for paper in previous_papers if track_key in paper.tracks]
        if not cached:
            raise RuntimeError(
                "No sources returned papers for %s. %s"
                % (track_key, "; ".join(source_errors))
            )
        selected = select_track_digest(
            cached,
            track_key,
            quota=int(limit or track.quota),
            topic_quotas=track.topic_quotas,
            relevance_threshold=track.relevance_threshold,
        )
        return TrackBuildResult(track_key, cached, selected, source_errors)

    papers = dedupe_papers(candidates)
    for paper in papers:
        apply_state(paper, paper_state.get(paper.id, {}))
    classify_and_score_track(papers, track, config.summary)
    accepted = [paper for paper in papers if track_key in paper.tracks]
    accepted.sort(key=lambda paper: _track_sort_key(paper, track_key))
    selected = select_track_digest(
        accepted,
        track_key,
        quota=int(limit or track.quota),
        topic_quotas=track.topic_quotas,
        relevance_threshold=track.relevance_threshold,
    )
    return TrackBuildResult(track_key, accepted, selected, source_errors)


def build_site_payload(
    results: List[TrackBuildResult],
    previous_papers: List[Paper],
    config: AppConfig,
    generated_at: str = None,
):
    canonical = merge_canonical_papers(
        [paper for result in results for paper in result.papers], previous_papers
    )
    track_payload = {}
    result_by_track = {result.track_key: result for result in results}
    for track_key, track in config.tracks.items():
        papers = [paper for paper in canonical if track_key in paper.tracks]
        papers.sort(key=lambda paper: _track_sort_key(paper, track_key))
        selected_ids = [
            paper.id for paper in result_by_track.get(track_key, TrackBuildResult(track_key, [], [], [])).selected
        ]
        track_payload[track_key] = {
            "key": track.key,
            "label": track.label,
            "cadence": track.cadence,
            "weekly_day": track.weekly_day,
            "quota": track.quota,
            "relevance_threshold": track.relevance_threshold,
            "topic_quotas": dict(track.topic_quotas),
            "paper_ids": [paper.id for paper in papers],
            "selected_ids": selected_ids,
        }
    source_errors = {
        result.track_key: list(result.source_errors)
        for result in results
        if result.source_errors
    }
    return {
        "generated_at": generated_at
        or _dt.datetime.now(_dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "site": asdict(config.site),
        "default_track": config.default_track,
        "tracks": track_payload,
        "topics": {
            "post_training": "Post-training",
            "llm_rl": "LLM RL",
            "llm_agent": "LLM Agent",
        },
        "foundations": [paper.id for paper in canonical if paper.foundation],
        "source_errors": source_errors,
        "papers": [asdict(paper) for paper in canonical],
    }


def dedupe_papers(papers: Iterable[Paper]) -> List[Paper]:
    result = []
    by_key = {}
    for paper in papers:
        key = _paper_key(paper)
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = paper
            result.append(paper)
            continue
        _merge_paper(existing, paper)
    return result


def merge_canonical_papers(
    current_papers: Iterable[Paper], previous_papers: Iterable[Paper]
) -> List[Paper]:
    merged = []
    by_id = {}
    for paper in list(current_papers) + list(previous_papers):
        existing = by_id.get(paper.id)
        if existing is None:
            by_id[paper.id] = paper
            merged.append(paper)
            continue
        _merge_paper(existing, paper)
    merged.sort(key=lambda paper: (-_published_timestamp(paper.published), paper.title.lower()))
    return merged


def _merge_paper(target: Paper, source: Paper) -> None:
    for field_name in ("tracks", "topics", "categories", "authors", "affiliations", "tags"):
        target_values = getattr(target, field_name)
        for value in getattr(source, field_name):
            if value not in target_values:
                target_values.append(value)
    for field_name in (
        "track_relevance",
        "track_relevance_evidence",
        "track_scores",
        "track_score_rationales",
        "track_score_breakdowns",
    ):
        getattr(target, field_name).update(getattr(source, field_name))
    for field_name in (
        "abstract",
        "doi",
        "venue",
        "venue_key",
        "generated_summary",
        "core_method",
        "practical_value",
        "analysis_signature",
    ):
        if not getattr(target, field_name) and getattr(source, field_name):
            setattr(target, field_name, getattr(source, field_name))
    if not target.primary_track and source.primary_track:
        target.primary_track = source.primary_track
    if not target.primary_topic and source.primary_topic:
        target.primary_topic = source.primary_topic
    target.citation_count = max(target.citation_count, source.citation_count)
    target.foundation = target.foundation or source.foundation
    target.foundation_score = max(target.foundation_score, source.foundation_score)
    for key, value in source.research_details.items():
        if key not in target.research_details or not target.research_details[key]:
            target.research_details[key] = value


def _paper_key(paper: Paper) -> str:
    if paper.id.startswith("arxiv:"):
        return paper.id.lower()
    if paper.doi:
        return "doi:" + paper.doi.lower().strip()
    title = re.sub(r"[^a-z0-9]+", "", paper.title.lower())
    return "title:%s:%s" % (title, paper.published[:4])


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
