"""Outgoing email. `console` logs, `smtp` sends to Mailpit in dev, `resend` is production."""

import smtplib
from dataclasses import dataclass
from email.message import EmailMessage

import httpx
import structlog

from doctune.core.config import get_settings

log = structlog.get_logger()


@dataclass(frozen=True)
class Email:
    to: str
    subject: str
    text: str


def send(email: Email) -> None:
    settings = get_settings()
    if settings.email_backend == "console":
        log.info("email", to=email.to, subject=email.subject)
        return
    if settings.email_backend == "smtp":
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = settings.email_from, email.to, email.subject
        msg.set_content(email.text)
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
            smtp.send_message(msg)
        return
    if settings.resend_api_key is None:
        raise RuntimeError("RESEND_API_KEY is not set")
    r = httpx.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {settings.resend_api_key.get_secret_value()}"},
        json={"from": settings.email_from, "to": [email.to], "subject": email.subject, "text": email.text},
        timeout=15,
    )
    r.raise_for_status()
