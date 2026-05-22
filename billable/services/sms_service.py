"""Twilio SMS — payment link now + follow-up reminder after delay."""
from __future__ import annotations

import logging
import threading

from twilioapis.http.auth.basic_auth import BasicAuthCredentials
from twilioapis.twilioapis_client import TwilioapisClient

from billable.config import get_settings

logger = logging.getLogger(__name__)


def build_client() -> TwilioapisClient:
    s = get_settings()
    return TwilioapisClient(
        basic_auth_credentials=BasicAuthCredentials(
            username=s.twilio_account_sid,
            password=s.twilio_auth_token,
        ),
    )


def _send(client: TwilioapisClient, to: str, body: str) -> str:
    s = get_settings()
    result = client.sms.create_message(
        s.twilio_account_sid,
        to,
        mfrom=s.twilio_from_number,
        body=body,
    )
    if not result.is_success():
        raise RuntimeError(f"Twilio send failed: {result.errors}")
    return result.body.sid


def send_payment_sms(
    client: TwilioapisClient,
    phone: str,
    client_name: str,
    amount: float,
    payment_url: str,
    follow_up_delay: int | None = None,
    on_follow_up: callable = None,
) -> str:
    """Send the initial payment SMS and schedule a reminder.

    Returns the initial message SID. The follow-up timer fires `on_follow_up`
    (if provided) after the SMS is sent.
    """
    initial = (
        f"Hi {client_name}, your invoice for ${amount:.2f} is ready.\n"
        f"Pay here: {payment_url}"
    )
    sid = _send(client, phone, initial)

    delay = (
        follow_up_delay
        if follow_up_delay is not None
        else get_settings().follow_up_delay_seconds
    )

    def _follow_up() -> None:
        try:
            reminder = (
                f"Reminder: your invoice for ${amount:.2f} is still outstanding.\n"
                f"Pay here: {payment_url}"
            )
            _send(client, phone, reminder)
            if on_follow_up:
                on_follow_up()
        except Exception:
            logger.exception("Follow-up SMS failed")

    threading.Timer(delay, _follow_up).start()
    return sid
