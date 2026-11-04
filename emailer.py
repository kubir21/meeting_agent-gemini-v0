"""Send the PDF report by email using Brevo's transactional email API."""
from __future__ import annotations

import base64
import logging
from pathlib import Path

import requests

import config

log = logging.getLogger(__name__)

BREVO_URL = "https://api.brevo.com/v3/smtp/email"


class EmailError(RuntimeError):
    """Sending the email failed."""


def send_report(pdf_path: Path, source_name: str, recipient: str = config.RECIPIENT_EMAIL) -> None:
    if not config.BREVO_API_KEY or config.BREVO_API_KEY.startswith("paste-"):
        raise EmailError("BREVO_API_KEY is not set in .env (see .env.example).")
    if not config.BREVO_SENDER_EMAIL or config.BREVO_SENDER_EMAIL.startswith("your."):
        raise EmailError("BREVO_SENDER_EMAIL is not set in .env (must be a verified sender in Brevo).")

    payload = {
        "sender": {"name": config.BREVO_SENDER_NAME, "email": config.BREVO_SENDER_EMAIL},
        "to": [{"email": recipient}],
        "subject": config.EMAIL_SUBJECT,
        "textContent": (
            "Hello,\n\n"
            f"Please find attached the automated analysis report for the video \"{source_name}\".\n"
            "It contains the extracted transcript and the contextual Q&A analysis.\n\n"
            "This email was generated automatically by the Video Analysis pipeline.\n"
        ),
        "attachment": [
            {
                "name": f"Video_Analysis_Report_{Path(source_name).stem}.pdf",
                "content": base64.b64encode(pdf_path.read_bytes()).decode("ascii"),
            }
        ],
    }
    headers = {"api-key": config.BREVO_API_KEY, "accept": "application/json", "content-type": "application/json"}

    try:
        resp = requests.post(BREVO_URL, json=payload, headers=headers, timeout=60)
    except requests.RequestException as exc:
        raise EmailError(f"Could not reach Brevo: {exc}") from exc

    if resp.status_code not in (200, 201):
        try:
            detail = resp.json().get("message", resp.text)
        except ValueError:
            detail = resp.text
        hint = ""
        if resp.status_code in (401, 403):
            hint = " Check BREVO_API_KEY and that your IP/account is allowed."
        elif resp.status_code == 400 and "sender" in str(detail).lower():
            hint = " Make sure BREVO_SENDER_EMAIL is a verified sender in Brevo."
        raise EmailError(f"Brevo rejected the email (HTTP {resp.status_code}): {detail}.{hint}")
    log.info("Report emailed to %s via Brevo (messageId=%s)", recipient, resp.json().get("messageId"))
