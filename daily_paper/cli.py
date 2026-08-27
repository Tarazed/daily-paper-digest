import argparse
import copy
import datetime as _dt
import json
import math
import os
import re
import sys
from dataclasses import asdict
from typing import List
from zoneinfo import ZoneInfo

from .arxiv import fetch_papers
from .config import load_config
from .dblp import fetch_dblp_papers
from .digest_state import load_digest_state, save_digest_state
from .email_template import (
    render_html,
    render_subject,
    render_text,
    render_track_html,
    render_track_text,
)
from .enrichment import enrich_papers, normalize_affiliations
from .filtering import prepare_papers, sort_papers
from .foundations import next_foundation_batch, select_foundations
from .mailer import MailConfigError, build_message, send_message
from .state import load_state
from .models import Paper
from .pipeline import build_site_payload, build_track, merge_canonical_papers
from .summarizer import (
    analyze_papers_for_site,
    copy_site_analysis,
    expected_analysis_signature,
    has_legacy_site_analysis,
    has_reusable_site_analysis,
    score_papers_with_llm,
    summarize_papers,
)
from .tracks import select_track_digest


def main(argv: List[str] = None) -> int:
    parser = argparse.ArgumentParser(prog="daily_paper")
    parser.add_argument("--config", default="config.toml", help="Path to config.toml")
    subparsers = parser.add_subparsers(dest="command")

    fetch_parser = subparsers.add_parser("fetch", help="Fetch and rank matching arXiv papers")
    fetch_parser.add_argument("--out", required=True, help="Output JSON path")
    fetch_parser.add_argument("--limit", type=int, default=None, help="Maximum papers to write")

    preview_parser = subparsers.add_parser("preview", help="Render an HTML email preview")
    preview_parser.add_argument("--out", required=True, help="Output HTML path")
    preview_parser.add_argument("--limit", type=int, default=None, help="Maximum papers to render")
    preview_parser.add_argument("--track", default=None, help="Research track to preview")
    preview_parser.add_argument(
        "--data", default="web/public/papers.json", help="Site data containing foundations"
    )

    send_parser = subparsers.add_parser("send", help="Send the daily digest email")
    send_parser.add_argument("--to", default=None, help="Recipient email. Overrides config default_to")
    send_parser.add_argument("--dry-run", action="store_true", help="Build email but do not send")
    send_parser.add_argument("--limit", type=int, default=None, help="Maximum papers to send")
    send_parser.add_argument("--track", default=None, help="Research track to send")
    send_parser.add_argument(
        "--data", default="web/public/papers.json", help="Site data containing foundations"
    )

    site_parser = subparsers.add_parser("site-data", help="Generate JSON data for the GitHub Pages app")
    site_parser.add_argument("--out", default="web/public/papers.json", help="Output JSON path")
    site_parser.add_argument("--limit", type=int, default=None, help="Maximum papers to include")
    site_parser.add_argument(
        "--track",
        action="append",
        default=[],
        help="Research track to update. Repeat for multiple tracks or use 'all'.",
    )

    backfill_parser = subparsers.add_parser(
        "backfill", help="Build the one-year LLM foundations collection"
    )
    backfill_parser.add_argument(
        "--out", default="web/public/papers.json", help="Output JSON path"
    )
    backfill_parser.add_argument("--days", type=int, default=365, help="Calendar-day window")
    backfill_parser.add_argument(
        "--per-topic", type=int, default=20, help="Maximum foundations per topic"
    )

    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 2

    config = load_config(args.config)
    try:
        if args.command == "fetch":
            return _fetch_command(args, config)
        if args.command == "preview":
            return _preview_command(args, config)
        if args.command == "send":
            return _send_command(args, config)
        if args.command == "site-data":
            return _site_data_command(args, config)
        if args.command == "backfill":
            return _backfill_command(args, config)
    except MailConfigError as exc:
        print("Email error: %s" % exc, file=sys.stderr)
        return 1
    except Exception as exc:
        print("Error: %s" % exc, file=sys.stderr)
        return 1
    return 2


def _fetch_command(args, config) -> int:
    papers = _load_ranked_papers(config, limit=args.limit or config.email.top_n)
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump([asdict(paper) for paper in papers], handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print("Wrote %d papers to %s" % (len(papers), args.out))
    return 0


def _preview_command(args, config) -> int:
    track_key = _validated_track_key(config, getattr(args, "track", None))
    track = config.tracks[track_key]
    digest_state = load_digest_state(config.digest_state_file)
    papers = _load_track_digest(
        config,
        track_key,
        limit=args.limit or track.quota,
        digest_state=digest_state,
        data_path=getattr(args, "data", "web/public/papers.json"),
    )
    pending_state = copy.deepcopy(digest_state)
    foundations = _pending_foundation_reviews(
        track_key,
        getattr(args, "data", "web/public/papers.json"),
        pending_state,
        exclude_ids={paper.id for paper in papers},
    )
    summarize_papers(papers + foundations, config.summary)
    title = render_subject("%s · %s" % (config.email.subject_prefix, track.label))
    html_body = render_track_html(papers, track, title, foundations)
    with open(args.out, "w", encoding="utf-8") as handle:
        handle.write(html_body)
    print("Wrote preview to %s" % args.out)
    return 0


def _send_command(args, config) -> int:
    to_value = args.to or config.email.default_to
    recipients = _parse_recipients(to_value)
    if not recipients:
        raise MailConfigError("A recipient is required. Pass --to or set email.default_to.")
    track_key = _validated_track_key(config, getattr(args, "track", None))
    track = config.tracks[track_key]
    digest_state = load_digest_state(config.digest_state_file)
    papers = _load_track_digest(
        config,
        track_key,
        limit=args.limit or track.quota,
        digest_state=digest_state,
        data_path=getattr(args, "data", "web/public/papers.json"),
    )
    pending_state = copy.deepcopy(digest_state)
    foundations = _pending_foundation_reviews(
        track_key,
        getattr(args, "data", "web/public/papers.json"),
        pending_state,
        exclude_ids={paper.id for paper in papers},
    )
    summarize_papers(papers + foundations, config.summary)
    subject = render_subject("%s · %s" % (config.email.subject_prefix, track.label))
    html_body = render_track_html(papers, track, subject, foundations)
    text_body = render_track_text(papers, track, subject, foundations)
    sender = os.getenv("SMTP_USER", "")
    if not sender and not args.dry_run:
        raise MailConfigError("SMTP_USER is required.")
    sender = sender or "dry-run@localhost"
    message = build_message(
        sender_name=config.email.sender_name,
        sender_email=sender,
        recipients=recipients,
        subject=subject,
        text_body=text_body,
        html_body=html_body,
    )
    if args.dry_run:
        print("Dry run: email built but not sent.")
        print("From: %s" % sender)
        print("To: %s" % ", ".join(recipients))
        print("Subject: %s" % subject)
        print("Papers: %d" % len(papers))
        return 0
    send_message(message)
    sent_ids = pending_state.sent_ids.setdefault(track_key, [])
    for paper in papers:
        if paper.id not in sent_ids:
            sent_ids.append(paper.id)
    pending_state.last_success[track_key] = _utc_timestamp()
    save_digest_state(config.digest_state_file, pending_state)
    print(
        "Sent %d new papers and %d foundation reviews to %s"
        % (len(papers), len(foundations), ", ".join(recipients))
    )
    return 0


def _site_data_command(args, config) -> int:
    limit = args.limit or config.site.default_limit
    previous_papers = _load_previous_site_papers(args.out)
    paper_state = load_state(config.state_file)
    digest_state = load_digest_state(config.digest_state_file)
    results, build_errors = _build_site_tracks(
        config,
        _track_keys_for_site_run(config, getattr(args, "track", [])),
        previous_papers,
        paper_state,
        digest_state,
    )
    if not results:
        raise RuntimeError("No research tracks could be built. " + "; ".join(build_errors))

    current_papers = merge_canonical_papers(
        [paper for result in results for paper in result.papers], []
    )
    current_paper_count = len(current_papers)
    papers = enrich_papers(
        current_papers,
        config.enrichment,
        llm_model=config.summary.model,
        llm_base_url=config.summary.base_url,
    )
    papers_to_analyze = _reuse_cached_site_analysis(papers, previous_papers, config.summary)
    cache_reused_count = len(papers) - len(papers_to_analyze)
    print(
        "Site analysis: reusing %d cached papers, analyzing %d new or changed papers."
        % (cache_reused_count, len(papers_to_analyze))
    )
    analyze_papers_for_site(papers_to_analyze, config.summary)
    papers = merge_canonical_papers(papers, previous_papers)
    papers = enrich_papers(
        papers,
        config.enrichment,
        llm_model=config.summary.model,
        llm_base_url=config.summary.base_url,
    )
    _clean_site_papers(papers)
    generated_at = (
        _dt.datetime.now(_dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    payload = build_site_payload(
        results, previous_papers=previous_papers, config=config, generated_at=generated_at
    )
    default_interest = config.tracks[config.default_track]
    payload.update(
        {
            "analysis_enabled": bool(_analysis_api_key(config.summary.provider)),
            "analysis_cache": {
                "reused": cache_reused_count,
                "analyzed": len(papers_to_analyze),
                "source": args.out,
            },
            "current_limit": limit,
            "current_paper_count": current_paper_count,
            "interests": {
                "arxiv_categories": default_interest.arxiv.categories,
                "include_keywords": default_interest.arxiv.include_keywords,
                "exclude_keywords": default_interest.arxiv.exclude_keywords,
                "dblp_venues": [venue.name for venue in default_interest.dblp.venues],
            },
            "build_errors": build_errors,
            "papers": [_paper_to_site_dict(paper) for paper in papers],
        }
    )
    out_dir = os.path.dirname(args.out)
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir)
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print("Wrote site data for %d papers to %s" % (len(papers), args.out))
    return 0


def _build_site_tracks(
    config, track_keys, previous_papers, paper_state, digest_state
):
    results = []
    build_errors = []
    for track_key in track_keys:
        try:
            results.append(
                build_track(
                    track_key,
                    config,
                    previous_papers=previous_papers,
                    paper_state=paper_state,
                    days_back=_delivery_days_back(
                        config.tracks[track_key], digest_state
                    ),
                )
            )
        except Exception as exc:
            build_errors.append("%s: %s" % (track_key, exc))
            print(
                "Warning: track build failed for %s; continuing. %s"
                % (track_key, exc),
                file=sys.stderr,
            )
    return results, build_errors


def _validated_track_key(config, requested=None) -> str:
    track_key = requested or config.default_track
    if track_key not in config.tracks:
        raise ValueError("Unknown research track: %s" % track_key)
    if not config.tracks[track_key].enabled:
        raise ValueError("Research track is disabled: %s" % track_key)
    return track_key


def _load_track_digest(
    config, track_key: str, limit: int, digest_state, data_path: str
) -> List[Paper]:
    previous_papers = _load_previous_site_papers(data_path)
    track = config.tracks[track_key]
    result = build_track(
        track_key,
        config,
        previous_papers=previous_papers,
        paper_state=load_state(config.state_file),
        limit=limit,
        days_back=_delivery_days_back(track, digest_state),
    )
    selected = select_track_digest(
        result.papers,
        track_key,
        quota=limit,
        topic_quotas=track.topic_quotas,
        sent_ids=digest_state.sent_ids.get(track_key, []),
        relevance_threshold=track.relevance_threshold,
    )
    return enrich_papers(
        selected,
        config.enrichment,
        llm_model=config.summary.model,
        llm_base_url=config.summary.base_url,
    )


def _pending_foundation_reviews(
    track_key: str, data_path: str, pending_state, exclude_ids=()
) -> List[Paper]:
    if track_key != "llm_systems":
        return []
    papers = [
        paper
        for paper in _load_previous_site_papers(data_path)
        if paper.foundation and paper.id not in set(exclude_ids or ())
    ]
    if not papers:
        return []
    return next_foundation_batch(papers, pending_state, count=3)


def _delivery_days_back(track, digest_state, now=None) -> int:
    cap = max(1, int(track.arxiv.days_back))
    last_success = digest_state.last_success.get(track.key, "")
    if not last_success:
        return cap
    try:
        completed = _dt.datetime.fromisoformat(last_success.replace("Z", "+00:00"))
    except ValueError:
        return cap
    current = now or _dt.datetime.now(_dt.timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=_dt.timezone.utc)
    if completed.tzinfo is None:
        completed = completed.replace(tzinfo=_dt.timezone.utc)
    elapsed_days = max(0.0, (current - completed).total_seconds() / 86400.0)
    return min(cap, max(1, int(math.ceil(elapsed_days))))


def _backfill_command(args, config) -> int:
    digest_state = load_digest_state(config.digest_state_file)
    if digest_state.cold_start_completed_at:
        print(
            "Cold start already completed at %s; no changes made."
            % digest_state.cold_start_completed_at
        )
        return 0
    if "llm_systems" not in config.tracks:
        raise ValueError("The llm_systems track is required for cold start.")

    previous_payload = _load_json_object(args.out)
    previous_papers = _load_previous_site_papers(args.out)
    result = build_track(
        "llm_systems",
        config,
        previous_papers=previous_papers,
        paper_state=load_state(config.state_file),
        days_back=max(1, int(args.days)),
        years_back=1,
    )
    current_papers = enrich_papers(
        result.papers,
        config.enrichment,
        llm_model=config.summary.model,
        llm_base_url=config.summary.base_url,
    )
    selection_report = {}
    foundations = select_foundations(
        current_papers,
        per_topic=max(0, int(args.per_topic)),
        report=selection_report,
    )
    foundations_to_analyze = _reuse_cached_site_analysis(
        foundations, previous_papers, config.summary
    )
    analyze_papers_for_site(foundations_to_analyze, config.summary)
    foundation_ids = {paper.id for paper in foundations}
    canonical = merge_canonical_papers(current_papers, previous_papers)
    for paper in canonical:
        if "llm_systems" in paper.tracks:
            paper.foundation = paper.id in foundation_ids
    _clean_site_papers(canonical)

    completed_at = _utc_timestamp()
    refreshed_result = type(result)(
        result.track_key, current_papers, result.selected, result.source_errors
    )
    payload = build_site_payload(
        [refreshed_result],
        previous_papers=previous_papers,
        config=config,
        generated_at=completed_at,
    )
    previous_payload.update(payload)
    previous_payload["papers"] = [_paper_to_site_dict(paper) for paper in canonical]
    previous_payload["foundations"] = [
        paper.id for paper in canonical if paper.foundation
    ]
    previous_payload["cold_start"] = {
        "completed_at": completed_at,
        "days": max(1, int(args.days)),
        "per_topic": max(0, int(args.per_topic)),
        "selected": len(foundations),
        **selection_report,
    }
    _write_json_atomic(args.out, previous_payload)

    digest_state.foundation_review_ids = _foundation_review_order(foundations)
    digest_state.foundation_review_cursor = 0
    digest_state.cold_start_completed_at = completed_at
    save_digest_state(config.digest_state_file, digest_state)
    print(
        "Cold start selected %d foundations and wrote %s"
        % (len(foundations), args.out)
    )
    return 0


def _track_keys_for_site_run(config, requested, now=None):
    requested = list(requested or [])
    if requested:
        values = list(config.tracks) if "all" in requested else requested
    else:
        values = [config.default_track]
        local_now = now or _dt.datetime.now(ZoneInfo("Asia/Shanghai"))
        gr_track = config.tracks.get("generative_rec")
        if gr_track and local_now.strftime("%A").lower() == gr_track.weekly_day.lower():
            values.append("generative_rec")
    result = []
    for value in values:
        if value not in config.tracks:
            raise ValueError("Unknown research track: %s" % value)
        if value not in result and config.tracks[value].enabled:
            result.append(value)
    return result


def _paper_to_site_dict(paper: Paper):
    values = asdict(paper)
    affiliations = normalize_affiliations(paper.affiliations)
    values["affiliations"] = affiliations
    values["display_affiliations"] = affiliations or ["Unknown affiliation"]
    values["published_date"] = paper.published_date
    return values


def _load_ranked_papers(config, limit: int, enrich_results: bool = True):
    state = load_state(config.state_file)
    papers = []
    source_errors = []
    try:
        papers.extend(fetch_papers(config.arxiv))
    except Exception as exc:
        source_errors.append("arXiv: %s" % exc)
        print("Warning: arXiv fetch failed; continuing with other sources. %s" % exc, file=sys.stderr)
    try:
        papers.extend(fetch_dblp_papers(config.dblp))
    except Exception as exc:
        source_errors.append("DBLP: %s" % exc)
        print("Warning: DBLP fetch failed; continuing with other sources. %s" % exc, file=sys.stderr)
    if not papers and source_errors:
        raise RuntimeError("No paper sources returned results. " + "; ".join(source_errors))
    papers = _dedupe_papers(papers)
    ranked = prepare_papers(papers, config.arxiv, state)
    candidate_count = _candidate_pool_size(limit, len(ranked))
    candidate_pool = ranked[:candidate_count] if candidate_count else ranked
    if enrich_results:
        candidate_pool = enrich_papers(
            candidate_pool,
            config.enrichment,
            llm_model=config.summary.model,
            llm_base_url=config.summary.base_url,
        )
    score_papers_with_llm(candidate_pool, config.summary)
    selected = sort_papers(candidate_pool)[:limit] if limit else sort_papers(candidate_pool)
    return selected


def _dedupe_papers(papers):
    seen = set()
    result = []
    for paper in papers:
        key = paper.doi.lower() if paper.doi else _normalize_title(paper.title)
        if key in seen:
            continue
        seen.add(key)
        result.append(paper)
    return result


def _normalize_title(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum())


def _parse_recipients(value: str) -> List[str]:
    if not value:
        return []
    return [item.strip() for item in value.replace(";", ",").split(",") if item.strip()]


def _candidate_pool_size(limit: int, available: int) -> int:
    if not limit:
        return available
    return min(available, max(limit * 3, limit + 20))


def _analysis_api_key(provider: str) -> str:
    if provider.lower() == "deepseek":
        return os.getenv("DEEPSEEK_API_KEY", "")
    return os.getenv("LLM_API_KEY", "")


def _select_site_papers(papers, limit: int):
    if not limit:
        return papers
    selected = list(papers[:limit])
    conference_papers = [paper for paper in papers if _is_conference_paper(paper)]
    if not conference_papers:
        return selected

    target_conference_count = min(len(conference_papers), max(1, min(5, limit // 5)))
    selected_ids = {paper.id for paper in selected}
    selected_conference_count = sum(1 for paper in selected if _is_conference_paper(paper))
    if selected_conference_count >= target_conference_count:
        return selected

    for conference_paper in conference_papers:
        if selected_conference_count >= target_conference_count:
            break
        if conference_paper.id in selected_ids:
            continue
        for index in range(len(selected) - 1, -1, -1):
            if _is_conference_paper(selected[index]):
                continue
            selected_ids.discard(selected[index].id)
            selected[index] = conference_paper
            selected_ids.add(conference_paper.id)
            selected_conference_count += 1
            break
    return selected


def _is_conference_paper(paper: Paper) -> bool:
    return (
        paper.status == "conference"
        or paper.source in ("DBLP", "OpenAlex", "Semantic Scholar")
        or bool(paper.venue_key)
    )


def _load_previous_site_papers(path: str) -> List[Paper]:
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception:
        return []
    values = payload.get("papers", []) if isinstance(payload, dict) else payload
    papers = []
    for item in values or []:
        if not isinstance(item, dict):
            continue
        paper = _paper_from_dict(item)
        if paper.id:
            papers.append(paper)
    return papers


def _reuse_cached_site_analysis(
    current_papers: List[Paper], previous_papers: List[Paper], summary_config
) -> List[Paper]:
    previous_by_id = {paper.id: paper for paper in previous_papers}
    papers_to_analyze = []
    for paper in current_papers:
        cached = previous_by_id.get(paper.id)
        if cached and not paper.affiliations and cached.affiliations:
            paper.affiliations = list(cached.affiliations)
        expected_signature = expected_analysis_signature(paper, summary_config)
        if cached and has_reusable_site_analysis(cached, summary_config, expected_signature):
            copy_site_analysis(cached, paper)
        elif cached and cached.updated == paper.updated and has_legacy_site_analysis(cached):
            copy_site_analysis(cached, paper)
            paper.analysis_signature = expected_signature
        else:
            papers_to_analyze.append(paper)
    return papers_to_analyze


def _merge_site_history(current_papers: List[Paper], previous_papers: List[Paper]) -> List[Paper]:
    merged = []
    seen = set()
    for paper in current_papers:
        if paper.id in seen:
            continue
        merged.append(paper)
        seen.add(paper.id)
    for paper in previous_papers:
        if paper.id in seen:
            continue
        merged.append(paper)
        seen.add(paper.id)
    return merged


def _clean_site_papers(papers: List[Paper]) -> None:
    import html

    for paper in papers:
        paper.title = _clean_display_text(paper.title, html)
        paper.authors = [_clean_display_author(value, html) for value in paper.authors]
        paper.affiliations = normalize_affiliations(
            [_clean_display_text(value, html) for value in paper.affiliations]
        )
        paper.categories = [value for value in paper.categories if value != "DBLP"]
        paper.generated_summary = _clean_display_text(paper.generated_summary, html)
        paper.core_method = _clean_display_text(paper.core_method, html)
        paper.innovation_points = [_clean_display_text(value, html) for value in paper.innovation_points]
        paper.experiment_results = [_clean_display_text(value, html) for value in paper.experiment_results]
        paper.ab_test_evidence = _clean_display_text(paper.ab_test_evidence, html)
        paper.limitations = [_clean_display_text(value, html) for value in paper.limitations]
        paper.practical_value = _clean_display_text(paper.practical_value, html)


def _clean_display_text(value: str, html_module) -> str:
    return html_module.unescape(str(value)).strip()


def _clean_display_author(value: str, html_module) -> str:
    text = _clean_display_text(value, html_module)
    return re.sub(r"\s+\d{4}$", "", text).strip()


def _paper_from_dict(values) -> Paper:
    tracks = list(values.get("tracks") or [])
    primary_track = str(values.get("primary_track", ""))
    if not tracks:
        tracks = ["generative_rec"]
        primary_track = "generative_rec"
    paper = Paper(
        id=str(values.get("id", "")),
        title=str(values.get("title", "")),
        authors=list(values.get("authors") or []),
        affiliations=list(values.get("affiliations") or []),
        published=str(values.get("published", "")),
        updated=str(values.get("updated", "")),
        abstract=str(values.get("abstract", "")),
        categories=list(values.get("categories") or []),
        primary_category=str(values.get("primary_category", "")),
        abs_url=str(values.get("abs_url", "")),
        pdf_url=str(values.get("pdf_url", "")),
        doi=str(values.get("doi", "")),
        source=str(values.get("source", "arXiv")),
        status=str(values.get("status", "preprint")),
        venue=str(values.get("venue", "")),
        venue_key=str(values.get("venue_key", "")),
        generated_summary=str(values.get("generated_summary", "")),
        core_method=str(values.get("core_method", "")),
        innovation_points=list(values.get("innovation_points") or []),
        experiment_results=list(values.get("experiment_results") or []),
        ab_test=str(values.get("ab_test", "unknown")),
        ab_test_evidence=str(values.get("ab_test_evidence", "")),
        limitations=list(values.get("limitations") or []),
        practical_value=str(values.get("practical_value", "")),
        analysis_basis=str(values.get("analysis_basis", "metadata")),
        analysis_status=str(values.get("analysis_status", "")),
        analysis_signature=str(values.get("analysis_signature", "")),
        tags=list(values.get("tags") or []),
        llm_score=int(values.get("llm_score", 0)),
        llm_score_rationale=str(values.get("llm_score_rationale", "")),
        preference_signals=list(values.get("preference_signals") or []),
        importance=str(values.get("importance", "normal")),
        read_status=str(values.get("read_status", "unread")),
        notes=str(values.get("notes", "")),
        score=int(values.get("score", 0)),
        tracks=tracks,
        primary_track=primary_track or tracks[0],
        topics=list(values.get("topics") or []),
        primary_topic=str(values.get("primary_topic", "")),
        track_relevance={
            str(key): int(value)
            for key, value in (values.get("track_relevance") or {}).items()
        },
        track_relevance_evidence={
            str(key): str(value)
            for key, value in (values.get("track_relevance_evidence") or {}).items()
        },
        track_scores={
            str(key): int(value)
            for key, value in (values.get("track_scores") or {}).items()
        },
        track_score_rationales={
            str(key): str(value)
            for key, value in (values.get("track_score_rationales") or {}).items()
        },
        track_score_breakdowns={
            str(track): {str(key): int(value) for key, value in (breakdown or {}).items()}
            for track, breakdown in (values.get("track_score_breakdowns") or {}).items()
        },
        foundation=bool(values.get("foundation", False)),
        foundation_score=int(values.get("foundation_score", 0) or 0),
        citation_count=int(values.get("citation_count", 0) or 0),
        research_details=dict(values.get("research_details") or {}),
    )
    return paper


def _load_json_object(path: str):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            values = json.load(handle)
    except (OSError, ValueError, TypeError):
        return {}
    return values if isinstance(values, dict) else {}


def _write_json_atomic(path: str, payload) -> None:
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    temporary_path = path + ".tmp"
    try:
        with open(temporary_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        try:
            os.unlink(temporary_path)
        except FileNotFoundError:
            pass


def _foundation_review_order(papers: List[Paper]) -> List[str]:
    by_topic = {}
    topic_order = []
    for paper in papers:
        topic = paper.primary_topic or "other"
        if topic not in by_topic:
            by_topic[topic] = []
            topic_order.append(topic)
        by_topic[topic].append(paper.id)
    result = []
    while any(by_topic.values()):
        for topic in topic_order:
            if by_topic[topic]:
                result.append(by_topic[topic].pop(0))
    return result


def _utc_timestamp() -> str:
    return (
        _dt.datetime.now(_dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
