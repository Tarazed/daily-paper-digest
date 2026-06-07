import datetime as _dt
import html
from typing import Iterable, List

from .models import Paper


def render_subject(prefix: str, date: str = None) -> str:
    day = date or _dt.date.today().isoformat()
    return "%s - %s" % (prefix, day)


def render_html(papers: Iterable[Paper], title: str = "Daily Paper Digest") -> str:
    items = list(papers)
    cards = "\n".join(_render_card(paper) for paper in items)
    return """<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
</head>
<body style="margin:0;padding:0;background:#f5f7fb;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;color:#1f2937;">
  <div style="max-width:760px;margin:0 auto;padding:24px 14px;">
    <div style="margin-bottom:18px;">
      <div style="font-size:12px;text-transform:uppercase;letter-spacing:.08em;color:#64748b;">Recommendation Systems</div>
      <h1 style="font-size:24px;line-height:1.25;margin:6px 0 4px;color:#0f172a;">{title}</h1>
      <div style="font-size:14px;color:#64748b;">{count} papers selected for RecSys, Generative Rec, LLM4Rec, and Agent4Rec.</div>
    </div>
    {cards}
  </div>
</body>
</html>""".format(
        title=html.escape(title), count=len(items), cards=cards or _empty_state()
    )


def render_text(papers: Iterable[Paper], title: str = "Daily Paper Digest") -> str:
    lines = [title, ""]
    for index, paper in enumerate(papers, 1):
        marker = "[HIGH] " if paper.importance == "high" else ""
        lines.extend(
            [
                "%d. %s%s" % (index, marker, paper.title),
                "Authors: %s" % ", ".join(paper.authors),
                "Affiliations: %s" % "; ".join(paper.display_affiliations),
                "%s %s · %s" % (paper.source, paper.status, paper.published_date),
                "Tags: %s" % ", ".join(paper.tags),
                "Summary: %s" % paper.generated_summary,
                "PDF: %s" % paper.pdf_url,
                "Paper: %s" % paper.abs_url,
                "",
            ]
        )
    return "\n".join(lines)


def _render_card(paper: Paper) -> str:
    high = paper.importance == "high"
    badge = (
        '<span style="display:inline-block;padding:3px 8px;border-radius:999px;'
        'font-size:12px;background:#fee2e2;color:#991b1b;margin-right:6px;">Important</span>'
        if high
        else ""
    )
    tags = "".join(
        '<span style="display:inline-block;padding:3px 8px;border-radius:999px;'
        'font-size:12px;background:#e0f2fe;color:#075985;margin-right:6px;margin-top:6px;">%s</span>'
        % html.escape(tag)
        for tag in paper.tags
    )
    authors = ", ".join(paper.authors[:8])
    if len(paper.authors) > 8:
        authors += " et al."
    links = (
        '<a href="{paper}" style="{link_style}">Paper</a>'
        '<a href="{pdf}" style="{link_style}">PDF</a>'
    ).format(
        paper=html.escape(paper.abs_url),
        pdf=html.escape(paper.pdf_url),
        link_style="display:inline-block;margin-right:10px;color:#2563eb;text-decoration:none;font-weight:600;",
    )
    notes = (
        '<div style="font-size:13px;color:#475569;margin-top:8px;">Note: %s</div>'
        % html.escape(paper.notes)
        if paper.notes
        else ""
    )
    return """<article style="background:#ffffff;border:1px solid #e5e7eb;border-radius:8px;padding:16px 18px;margin:0 0 14px;">
  <div style="margin-bottom:8px;">{badge}{tags}</div>
  <h2 style="font-size:18px;line-height:1.35;margin:0 0 8px;color:#111827;">{title}</h2>
  <div style="font-size:13px;line-height:1.45;color:#475569;margin-bottom:4px;">{authors}</div>
  <div style="font-size:13px;line-height:1.45;color:#64748b;margin-bottom:8px;">{affiliations}</div>
  <div style="font-size:13px;color:#64748b;margin-bottom:10px;">{source} {status}{venue} · {date}</div>
  <p style="font-size:14px;line-height:1.65;margin:0 0 12px;color:#1f2937;">{summary}</p>
  <div style="font-size:14px;">{links}</div>
  {notes}
</article>""".format(
        badge=badge,
        tags=tags,
        title=html.escape(paper.title),
        authors=html.escape(authors or "Unknown authors"),
        affiliations=html.escape(" · ".join(paper.display_affiliations)),
        source=html.escape(paper.source),
        status=html.escape(paper.status),
        venue=html.escape(" · " + paper.venue if paper.venue else ""),
        date=html.escape(paper.published_date),
        summary=html.escape(paper.generated_summary),
        links=links,
        notes=notes,
    )


def _empty_state() -> str:
    return '<div style="background:#fff;border:1px solid #e5e7eb;border-radius:8px;padding:18px;">No matching papers found.</div>'
