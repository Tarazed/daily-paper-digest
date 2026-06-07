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
from .summarizer import analyze_papers_for_site, summarize_papers


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
    analyze_papers_for_site(papers, config.summary)
    payload = {
        "generated_at": _dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "site": asdict(config.site),
        "analysis_enabled": bool(_analysis_api_key(config.summary.provider)),
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
