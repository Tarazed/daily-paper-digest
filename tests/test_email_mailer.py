import json
from dataclasses import asdict
from types import SimpleNamespace

import pytest

from daily_paper.cli import _send_command
from daily_paper.config import load_config
from daily_paper.digest_state import DigestState, load_digest_state, save_digest_state
from daily_paper.email_template import (
    render_html,
    render_text,
    render_track_html,
    render_track_text,
)
from daily_paper.mailer import build_message, send_message
from daily_paper.models import Paper


def paper():
    return Paper(
        id="arxiv:2606.01234",
        title="LLM4Rec for Sequential Recommendation",
        authors=["Alice Zhang", "Bob Lee"],
        affiliations=["Stanford University", "Google DeepMind"],
        published="2026-06-07T00:00:00Z",
        updated="2026-06-07T00:00:00Z",
        abstract="Abstract.",
        categories=["cs.IR"],
        primary_category="cs.IR",
        abs_url="https://arxiv.org/abs/2606.01234",
        pdf_url="https://arxiv.org/pdf/2606.01234",
        generated_summary="这篇论文研究 LLM4Rec。",
        tags=["LLM4Rec", "Sequential Rec"],
        importance="high",
    )


def test_render_email_contains_required_fields():
    html = render_html([paper()], title="Daily Paper Digest - 2026-06-07")
    text = render_text([paper()], title="Daily Paper Digest - 2026-06-07")

    assert "LLM4Rec for Sequential Recommendation" in html
    assert "Stanford University" in html
    assert "Important" in html
    assert "https://arxiv.org/pdf/2606.01234" in html
    assert "[HIGH]" in text
    assert "Tags: LLM4Rec, Sequential Rec" in text


def test_build_message_and_send_with_mock_smtp(monkeypatch):
    sent = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            sent["host"] = host
            sent["port"] = port
            sent["timeout"] = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def ehlo(self):
            sent["ehlo"] = sent.get("ehlo", 0) + 1

        def starttls(self):
            sent["starttls"] = True

        def login(self, user, password):
            sent["login"] = (user, password)

        def send_message(self, message):
            sent["message"] = message

    monkeypatch.setenv("SMTP_USER", "sender@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    monkeypatch.setattr("smtplib.SMTP_SSL", FakeSMTP)

    message = build_message(
        sender_name="Digest",
        sender_email="sender@example.com",
        recipients=["reader@example.com"],
        subject="Daily Paper Digest",
        text_body="text",
        html_body="<strong>html</strong>",
    )
    send_message(message)

    assert sent["host"] == "smtp.qq.com"
    assert sent["login"] == ("sender@example.com", "secret")
    assert sent["message"]["To"] == "reader@example.com"


def test_llm_email_has_new_and_classic_sections():
    config = load_config("config.toml")
    current = paper()
    current.tracks = ["llm_systems"]
    current.primary_track = "llm_systems"
    current.topics = ["llm_rl"]
    current.primary_topic = "llm_rl"
    current.track_scores = {"llm_systems": 88}
    current.track_score_rationales = {"llm_systems": "奖励设计扎实。"}
    current.research_details = {
        "training_objective": "提升可验证推理",
        "feedback_source": "规则奖励",
    }
    classic = paper()
    classic.id = "arxiv:classic"
    classic.title = "Classic Language Model RL"
    classic.tracks = ["llm_systems"]
    classic.primary_track = "llm_systems"
    classic.topics = ["llm_rl"]
    classic.primary_topic = "llm_rl"

    html = render_track_html(
        [current], config.tracks["llm_systems"], "Daily", [classic]
    )
    text = render_track_text(
        [current], config.tracks["llm_systems"], "Daily", [classic]
    )

    assert "今日新论文" in html
    assert "经典回顾" in html
    assert "训练目标" in html
    assert "提升可验证推理" in html
    assert "经典回顾" in text


def test_gr_email_keeps_ab_evidence_without_classic_section():
    config = load_config("config.toml")
    gr = paper()
    gr.tracks = ["generative_rec"]
    gr.primary_track = "generative_rec"
    gr.ab_test = "yes"
    gr.ab_test_evidence = "线上 A/B 提升 2%。"

    html = render_track_html([gr], config.tracks["generative_rec"], "Weekly GR")

    assert "线上 A/B" in html
    assert "线上 A/B 提升 2%。" in html
    assert "经典回顾" not in html


def test_successful_send_advances_track_and_foundation_state(tmp_path, monkeypatch):
    config = load_config("config.toml")
    config.digest_state_file = str(tmp_path / "digest_state.json")
    current = paper()
    current.id = "arxiv:new"
    current.tracks = ["llm_systems"]
    current.primary_track = "llm_systems"
    current.topics = ["llm_rl"]
    current.primary_topic = "llm_rl"
    classic = paper()
    classic.id = "arxiv:classic"
    classic.foundation = True
    classic.tracks = ["llm_systems"]
    data_path = tmp_path / "papers.json"
    data_path.write_text(json.dumps({"papers": [asdict(classic)]}), encoding="utf-8")
    save_digest_state(
        config.digest_state_file,
        DigestState(foundation_review_ids=[classic.id]),
    )
    monkeypatch.setenv("SMTP_USER", "sender@example.com")
    monkeypatch.setattr(
        "daily_paper.cli._load_track_digest", lambda *args, **kwargs: [current]
    )
    monkeypatch.setattr("daily_paper.cli.summarize_papers", lambda papers, config: papers)
    sent = []
    monkeypatch.setattr("daily_paper.cli.send_message", lambda message: sent.append(message))

    result = _send_command(
        SimpleNamespace(
            to="reader@example.com",
            dry_run=False,
            limit=None,
            track="llm_systems",
            data=str(data_path),
        ),
        config,
    )

    state = load_digest_state(config.digest_state_file)
    assert result == 0
    assert len(sent) == 1
    assert state.sent_ids["llm_systems"] == ["arxiv:new"]
    assert state.foundation_review_cursor == 1
    assert state.last_success["llm_systems"].endswith("Z")


@pytest.mark.parametrize("mode", ["dry_run", "failed_send"])
def test_unsuccessful_send_does_not_advance_digest_state(tmp_path, monkeypatch, mode):
    config = load_config("config.toml")
    config.digest_state_file = str(tmp_path / "digest_state.json")
    current = paper()
    current.id = "arxiv:new"
    current.tracks = ["llm_systems"]
    current.primary_track = "llm_systems"
    classic = paper()
    classic.id = "arxiv:classic"
    classic.foundation = True
    classic.tracks = ["llm_systems"]
    data_path = tmp_path / "papers.json"
    data_path.write_text(json.dumps({"papers": [asdict(classic)]}), encoding="utf-8")
    original = DigestState(foundation_review_ids=[classic.id])
    save_digest_state(config.digest_state_file, original)
    monkeypatch.setenv("SMTP_USER", "sender@example.com")
    monkeypatch.setattr(
        "daily_paper.cli._load_track_digest", lambda *args, **kwargs: [current]
    )
    monkeypatch.setattr("daily_paper.cli.summarize_papers", lambda papers, config: papers)
    if mode == "failed_send":
        monkeypatch.setattr(
            "daily_paper.cli.send_message",
            lambda message: (_ for _ in ()).throw(RuntimeError("smtp failed")),
        )
    args = SimpleNamespace(
        to="reader@example.com",
        dry_run=mode == "dry_run",
        limit=None,
        track="llm_systems",
        data=str(data_path),
    )

    if mode == "failed_send":
        with pytest.raises(RuntimeError, match="smtp failed"):
            _send_command(args, config)
    else:
        assert _send_command(args, config) == 0

    assert load_digest_state(config.digest_state_file) == original
