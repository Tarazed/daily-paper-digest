from daily_paper.email_template import render_html, render_text
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
