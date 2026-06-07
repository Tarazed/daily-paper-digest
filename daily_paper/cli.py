import argparse
import datetime as _dt
import json
import os
import sys
from dataclasses import asdict
from typing import List

from .arxiv import fetch_papers
from .config import load_config
from .dblp import fetch_dblp_papers
from .email_template import render_html, render_subject, render_text
from .enrichment import enrich_papers
from .filtering import prepare_papers
from .mailer import MailConfigError, build_message, send_message
from .state import load_state
from .models import Paper
from .summarizer import (
    analyze_papers_for_site,
    copy_site_analysis,
    expected_analysis_signature,
    has_reusable_site_analysis,
    summarize_papers,
)


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

    send_parser = subparsers.add_parser("send", help="Send the daily digest email")
    send_parser.add_argument("--to", default=None, help="Recipient email. Overrides config default_to")
    send_parser.add_argument("--dry-run", action="store_true", help="Build email but do not send")
    send_parser.add_argument("--limit", type=int, default=None, help="Maximum papers to send")

    site_parser = subparsers.add_parser("site-data", help="Generate JSON data for the GitHub Pages app")
    site_parser.add_argument("--out", default="web/public/papers.json", help="Output JSON path")
    site_parser.add_argument("--limit", type=int, default=None, help="Maximum papers to include")

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
    papers = _load_ranked_papers(config, limit=args.limit or config.email.top_n)
    summarize_papers(papers, config.summary)
    title = render_subject(config.email.subject_prefix)
    html_body = render_html(papers, title=title)
    with open(args.out, "w", encoding="utf-8") as handle:
        handle.write(html_body)
    print("Wrote preview to %s" % args.out)
    return 0


def _send_command(args, config) -> int:
    to_value = args.to or config.email.default_to
    recipients = _parse_recipients(to_value)
    if not recipients:
        raise MailConfigError("A recipient is required. Pass --to or set email.default_to.")
    papers = _load_ranked_papers(config, limit=args.limit or config.email.top_n)
    summarize_papers(papers, config.summary)
    subject = render_subject(config.email.subject_prefix)
    html_body = render_html(papers, title=subject)
    text_body = render_text(papers, title=subject)
    sender = os.getenv("SMTP_USER", "")
    if not sender:
        raise MailConfigError("SMTP_USER is required.")
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
    print("Sent %d papers to %s" % (len(papers), ", ".join(recipients)))
    return 0


def _site_data_command(args, config) -> int:
    limit = args.limit or config.site.default_limit
    candidates = _load_ranked_papers(config, limit=limit * 2)
    papers = _select_site_papers(candidates, limit)
    current_paper_count = len(papers)
    previous_papers = _load_previous_site_papers(args.out)
    papers_to_analyze = _reuse_cached_site_analysis(papers, previous_papers, config.summary)
    analyze_papers_for_site(papers_to_analyze, config.summary)
    papers = _merge_site_history(papers, previous_papers)
    payload = {
        "generated_at": _dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "site": asdict(config.site),
        "analysis_enabled": bool(_analysis_api_key(config.summary.provider)),
        "current_limit": limit,
        "current_paper_count": current_paper_count,
        "interests": {
            "arxiv_categories": config.arxiv.categories,
            "include_keywords": config.arxiv.include_keywords,
            "exclude_keywords": config.arxiv.exclude_keywords,
            "dblp_venues": [venue.name for venue in config.dblp.venues],
        },
        "papers": [asdict(paper) for paper in papers],
    }
    out_dir = os.path.dirname(args.out)
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir)
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print("Wrote site data for %d papers to %s" % (len(papers), args.out))
    return 0


def _load_ranked_papers(config, limit: int):
    state = load_state(config.state_file)
    papers = []
    papers.extend(fetch_papers(config.arxiv))
    papers.extend(fetch_dblp_papers(config.dblp))
    papers = _dedupe_papers(papers)
    ranked = prepare_papers(papers, config.arxiv, state)
    selected = ranked[:limit] if limit else ranked
    return enrich_papers(
        selected,
        config.enrichment,
        llm_model=config.summary.model,
        llm_base_url=config.summary.base_url,
    )


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


def _analysis_api_key(provider: str) -> str:
    if provider.lower() == "deepseek":
        return os.getenv("DEEPSEEK_API_KEY", "")
    return os.getenv("LLM_API_KEY", "")


def _select_site_papers(papers, limit: int):
    if not limit:
        return papers
    arxiv_target = max(1, int(round(limit * 0.7)))
    arxiv = [paper for paper in papers if paper.source == "arXiv"]
    dblp = [paper for paper in papers if paper.source == "DBLP"]
    selected = arxiv[:arxiv_target] + dblp[: max(0, limit - arxiv_target)]
    if len(selected) < limit:
        selected_ids = {paper.id for paper in selected}
        for paper in papers:
            if paper.id not in selected_ids:
                selected.append(paper)
                selected_ids.add(paper.id)
            if len(selected) >= limit:
                break
    return selected[:limit]


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
        expected_signature = expected_analysis_signature(paper, summary_config)
        if cached and has_reusable_site_analysis(cached, summary_config, expected_signature):
            copy_site_analysis(cached, paper)
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


def _paper_from_dict(values) -> Paper:
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
        importance=str(values.get("importance", "normal")),
        read_status=str(values.get("read_status", "unread")),
        notes=str(values.get("notes", "")),
        score=int(values.get("score", 0)),
    )
    return paper
