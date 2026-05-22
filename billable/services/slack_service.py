"""Slack — post a Block Kit receipt to an incoming webhook."""
from __future__ import annotations

import requests

from billable.config import get_settings


def _receipt_blocks(
    meeting_title: str,
    client_email: str,
    amount: float,
    duration_minutes: int,
    payment_url: str,
) -> list[dict]:
    return [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": ":moneybag: Invoice sent"},
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*{meeting_title}*\n"
                    f"*Client:* {client_email}\n"
                    f"*Duration:* {duration_minutes} min   *Amount:* ${amount:.2f}"
                ),
            },
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "View Invoice"},
                    "url": payment_url,
                }
            ],
        },
    ]


def post_receipt(
    meeting_title: str,
    client_email: str,
    amount: float,
    duration_minutes: int,
    payment_url: str,
    webhook_url: str | None = None,
) -> None:
    url = webhook_url or get_settings().slack_webhook_url
    if not url:
        raise RuntimeError("SLACK_WEBHOOK_URL not configured")

    blocks = _receipt_blocks(
        meeting_title, client_email, amount, duration_minutes, payment_url
    )
    r = requests.post(url, json={"blocks": blocks}, timeout=10)
    r.raise_for_status()


def post_followup_sent(client_email: str, webhook_url: str | None = None) -> None:
    url = webhook_url or get_settings().slack_webhook_url
    if not url:
        raise RuntimeError("SLACK_WEBHOOK_URL not configured")

    r = requests.post(
        url,
        json={"text": f":bell: Follow-up SMS sent to {client_email}"},
        timeout=10,
    )
    r.raise_for_status()
