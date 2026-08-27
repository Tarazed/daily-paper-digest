import datetime as _dt
import html
from typing import Iterable, List

from .models import Paper


RESEARCH_DETAIL_LABELS = {
    "training_objective": "训练目标",
    "feedback_source": "反馈 / 奖励来源",
    "model_data_scale": "模型 / 数据规模",
    "key_benchmarks": "关键基准",
    "artifacts": "开源产物",
    "agent_environment": "Agent 环境",
    "agent_mechanism": "Agent 机制",
    "interaction_horizon": "交互时域",
    "agent_evaluation": "Agent 评测",
}
TOPIC_LABELS = {
    "post_training": "Post-training",
    "llm_rl": "LLM RL",
    "llm_agent": "LLM Agent",
}


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
      <div style="font-size:14px;color:#64748b;">{count} papers selected for LLM4Rec, Semantic ID, Generative Rec, and Agent4Rec.</div>
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


def render_track_html(
    papers: Iterable[Paper], track, title: str, foundation_papers=()
) -> str:
    items = list(papers)
    classics = list(foundation_papers or ()) if track.key == "llm_systems" else []
    current_cards = "\n".join(_render_track_card(paper, track.key) for paper in items)
    classic_section = ""
    if classics:
        classic_cards = "\n".join(
            _render_track_card(paper, track.key, classic=True) for paper in classics
        )
        classic_section = _render_section("经典回顾", classic_cards)
    section_title = "今日新论文" if track.cadence == "daily" else "本周新论文"
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
      <div style="font-size:12px;text-transform:uppercase;letter-spacing:.08em;color:#64748b;">{track_label}</div>
      <h1 style="font-size:24px;line-height:1.25;margin:6px 0 4px;color:#0f172a;">{title}</h1>
      <div style="font-size:14px;color:#64748b;">{count} 篇新论文{classic_count}。</div>
    </div>
    {current_section}
    {classic_section}
  </div>
</body>
</html>""".format(
        title=html.escape(title),
        track_label=html.escape(track.label),
        count=len(items),
        classic_count=("，另含 %d 篇经典回顾" % len(classics)) if classics else "",
        current_section=_render_section(section_title, current_cards or _empty_state()),
        classic_section=classic_section,
    )


def render_track_text(
    papers: Iterable[Paper], track, title: str, foundation_papers=()
) -> str:
    items = list(papers)
    classics = list(foundation_papers or ()) if track.key == "llm_systems" else []
    section_title = "今日新论文" if track.cadence == "daily" else "本周新论文"
    lines = [title, track.label, "", section_title, ""]
    lines.extend(_render_track_text_items(items, track.key))
    if classics:
        lines.extend(["经典回顾", ""])
        lines.extend(_render_track_text_items(classics, track.key, classic=True))
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


def _render_track_card(paper: Paper, track_key: str, classic: bool = False) -> str:
    card = _render_card(paper)
    badges = []
    if classic:
        badges.append("经典回顾")
    if paper.primary_topic:
        badges.append(TOPIC_LABELS.get(paper.primary_topic, paper.primary_topic))
    badge_html = "".join(
        '<span style="display:inline-block;padding:3px 8px;border-radius:999px;'
        'font-size:12px;background:#ede9fe;color:#5b21b6;margin-right:6px;">%s</span>'
        % html.escape(label)
        for label in badges
    )
    details = []
    score = paper.track_scores.get(track_key)
    if score is not None:
        rationale = paper.track_score_rationales.get(track_key, "")
        details.append(
            "<strong>Track score:</strong> %d/100%s"
            % (score, " · " + html.escape(rationale) if rationale else "")
        )
    if track_key == "llm_systems":
        for key, label in RESEARCH_DETAIL_LABELS.items():
            value = paper.research_details.get(key)
            if not value:
                continue
            if isinstance(value, list):
                value = "、".join(str(item) for item in value)
            details.append(
                "<strong>%s:</strong> %s"
                % (html.escape(label), html.escape(str(value)))
            )
    elif paper.ab_test_evidence:
        details.append(
            "<strong>线上 A/B:</strong> %s" % html.escape(paper.ab_test_evidence)
        )
    extra = ""
    if badge_html or details:
        detail_html = "".join(
            '<div style="font-size:13px;line-height:1.55;color:#475569;margin-top:5px;">%s</div>'
            % detail
            for detail in details
        )
        extra = (
            '<div style="border-top:1px solid #e5e7eb;margin-top:12px;padding-top:10px;">'
            + badge_html
            + detail_html
            + "</div>"
        )
    return card.replace("</article>", extra + "</article>")


def _render_section(title: str, content: str) -> str:
    return (
        '<section style="margin-bottom:22px;">'
        '<h2 style="font-size:18px;margin:0 0 10px;color:#0f172a;">%s</h2>%s</section>'
        % (html.escape(title), content)
    )


def _render_track_text_items(papers, track_key: str, classic: bool = False):
    lines = []
    for index, paper in enumerate(papers, 1):
        prefix = "[经典] " if classic else ""
        lines.extend(
            [
                "%d. %s%s" % (index, prefix, paper.title),
                "Authors: %s" % ", ".join(paper.authors),
                "Topic: %s"
                % TOPIC_LABELS.get(paper.primary_topic, paper.primary_topic or "-") ,
                "Track score: %s"
                % (
                    paper.track_scores.get(track_key)
                    if track_key in paper.track_scores
                    else "-"
                ),
                "Summary: %s" % paper.generated_summary,
            ]
        )
        if track_key == "llm_systems":
            for key, label in RESEARCH_DETAIL_LABELS.items():
                value = paper.research_details.get(key)
                if value:
                    if isinstance(value, list):
                        value = "、".join(str(item) for item in value)
                    lines.append("%s: %s" % (label, value))
        elif paper.ab_test_evidence:
            lines.append("线上 A/B: %s" % paper.ab_test_evidence)
        lines.extend(["PDF: %s" % paper.pdf_url, "Paper: %s" % paper.abs_url, ""])
    return lines


def _empty_state() -> str:
    return '<div style="background:#fff;border:1px solid #e5e7eb;border-radius:8px;padding:18px;">No matching papers found.</div>'
