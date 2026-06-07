import os
import smtplib
from email.message import EmailMessage
from email.utils import formataddr
from typing import List


class MailConfigError(RuntimeError):
    pass


def build_message(
    sender_name: str,
    sender_email: str,
    recipients: List[str],
    subject: str,
    text_body: str,
    html_body: str,
) -> EmailMessage:
    message = EmailMessage()
    message["From"] = formataddr((sender_name, sender_email))
    message["To"] = ", ".join(recipients)
    message["Subject"] = subject
    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")
    return message


def send_message(message: EmailMessage) -> None:
    host = os.getenv("SMTP_HOST", "smtp.qq.com")
    port = int(os.getenv("SMTP_PORT", "465"))
    user = os.getenv("SMTP_USER", "")
    password = os.getenv("SMTP_PASSWORD")
    if not user:
        raise MailConfigError("SMTP_USER is required.")
    if not password:
        raise MailConfigError("SMTP_PASSWORD is required for real email sending.")
    try:
        use_ssl = os.getenv("SMTP_SSL", "true").lower() in ("1", "true", "yes")
        if use_ssl:
            with smtplib.SMTP_SSL(host, port, timeout=30) as smtp:
                smtp.login(user, password)
                smtp.send_message(message)
        else:
            with smtplib.SMTP(host, port, timeout=30) as smtp:
                smtp.ehlo()
                smtp.starttls()
                smtp.ehlo()
                smtp.login(user, password)
                smtp.send_message(message)
    except smtplib.SMTPAuthenticationError as exc:
        raise MailConfigError("SMTP authentication failed. Check QQ Mail authorization code.") from exc
    except smtplib.SMTPServerDisconnected as exc:
        raise MailConfigError(
            "SMTP server disconnected during authentication. Check QQ Mail SMTP access and authorization code."
        ) from exc
    except OSError as exc:
        raise MailConfigError("SMTP network error: %s" % exc) from exc
