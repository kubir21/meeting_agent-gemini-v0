"""Send a report PDF by email, via Brevo's API or Gmail SMTP (config.EMAIL_PROVIDER)."""
from __future__ import annotations

import base64
import html
import logging
import re
import smtplib
import ssl
from email.message import EmailMessage

import requests

import config

log = logging.getLogger(__name__)

BREVO_URL = "https://api.brevo.com/v3/smtp/email"
_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9](?:[A-Za-z0-9\-]*[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9\-]*[A-Za-z0-9])?)*\.[A-Za-z]{2,}$")


class EmailError(RuntimeError):
    """Sending the email failed (message is safe to show to the user)."""


def is_valid_email(addr: str) -> bool:
    addr = (addr or "").strip()
    return 0 < len(addr) <= 254 and ".." not in addr and bool(_EMAIL_RE.match(addr))


def _bodies(company: str, report_id: str, source_name: str) -> tuple[str, str]:
    text = (
        "Hello,\n\n"
        f"Your video analysis report for \"{company}\" is attached as a PDF.\n\n"
        f"Report ID: {report_id}\n"
        f"Source video: {source_name or 'Not available'}\n\n"
        "This email was sent automatically by Video Insights.\n"
    )
    h = lambda s: html.escape(str(s))
    page = (
        "<div style=\"font-family:Arial,sans-serif;color:#111827;line-height:1.5\">"
        "<p>Hello,</p>"
        f"<p>Your video analysis report for <strong>{h(company)}</strong> is attached as a PDF.</p>"
        f"<p style=\"color:#6b7280;font-size:13px\">Report ID: {h(report_id)}<br>"
        f"Source video: {h(source_name or 'Not available')}</p>"
        "<p style=\"color:#6b7280;font-size:13px\">This email was sent automatically by Video Insights.</p></div>"
    )
    return text, page


def _send_brevo(recipient: str, pdf: bytes, filename: str, text: str, page: str) -> None:
    if not config.BREVO_API_KEY or config.BREVO_API_KEY.startswith("paste-"):
        raise EmailError("Email is not configured: BREVO_API_KEY is missing in .env.")
    payload = {
        "sender": {"name": config.SENDER_NAME, "email": config.SENDER_EMAIL},
        "to": [{"email": recipient}],
        "subject": config.EMAIL_SUBJECT,
        "textContent": text,
        "htmlContent": page,
        "attachment": [{"name": filename, "content": base64.b64encode(pdf).decode("ascii")}],
    }
    headers = {"api-key": config.BREVO_API_KEY, "accept": "application/json", "content-type": "application/json"}
    try:
        resp = requests.post(BREVO_URL, json=payload, headers=headers, timeout=60)
    except requests.RequestException as exc:
        raise EmailError("Could not reach the email service. Please check your internet connection.") from exc
    if resp.status_code in (200, 201):
        log.info("Brevo accepted email (messageId=%s)", resp.json().get("messageId"))
        return
    try:
        detail = str(resp.json().get("message", resp.text))
    except ValueError:
        detail = resp.text
    log.warning("Brevo error %s: %s", resp.status_code, detail)
    low = detail.lower()
    if resp.status_code in (401, 403) and "ip" in low:
        raise EmailError("The email service blocked this network (Brevo IP restriction). "
                         "Turn off IP blocking in Brevo, or switch EMAIL_PROVIDER to gmail.")
    if resp.status_code in (401, 403):
        raise EmailError("The email service rejected the API key. Please check BREVO_API_KEY.")
    if "sender" in low:
        raise EmailError(f"The sender address {config.SENDER_EMAIL} is not verified in Brevo.")
    raise EmailError(f"The email service could not send this message (HTTP {resp.status_code}).")


def _send_gmail(recipient: str, pdf: bytes, filename: str, text: str, page: str) -> None:
    if not config.GMAIL_APP_PASSWORD:
        raise EmailError("Email is not configured: GMAIL_APP_PASSWORD is missing in .env.")
    msg = EmailMessage()
    msg["Subject"] = config.EMAIL_SUBJECT
    msg["From"] = f"{config.SENDER_NAME} <{config.SENDER_EMAIL}>"
    msg["To"] = recipient
    msg.set_content(text)
    msg.add_alternative(page, subtype="html")
    msg.add_attachment(pdf, maintype="application", subtype="pdf", filename=filename)
    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=60) as server:
            server.starttls(context=ssl.create_default_context())
            server.login(config.SENDER_EMAIL, config.GMAIL_APP_PASSWORD)
            server.send_message(msg)
    except smtplib.SMTPAuthenticationError as exc:
        raise EmailError("Gmail rejected the login. Use a Gmail App Password in GMAIL_APP_PASSWORD.") from exc
    except smtplib.SMTPRecipientsRefused as exc:
        raise EmailError("Gmail refused this recipient address.") from exc
    except (smtplib.SMTPException, OSError) as exc:
        log.warning("Gmail SMTP error: %s", exc)
        raise EmailError("Could not send through Gmail. Please try again.") from exc


def send_report(recipient: str, pdf_bytes: bytes, filename: str, company: str,
                report_id: str, source_name: str = "") -> None:
    """Email `pdf_bytes` to `recipient`. Raises EmailError with a user-safe message."""
    recipient = (recipient or "").strip()
    if not is_valid_email(recipient):
        raise EmailError("Please enter a valid email address.")
    text, page = _bodies(company, report_id, source_name)
    provider = config.EMAIL_PROVIDER
    if provider == "gmail":
        _send_gmail(recipient, pdf_bytes, filename, text, page)
    elif provider == "brevo":
        _send_brevo(recipient, pdf_bytes, filename, text, page)
    else:
        raise EmailError(f"Unknown EMAIL_PROVIDER '{provider}'. Use 'brevo' or 'gmail'.")
    log.info("Report %s emailed to %s via %s", report_id, recipient, provider)
