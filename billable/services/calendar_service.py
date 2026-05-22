"""Google Calendar polling — finds recently-ended [BILLABLE] meetings."""
from __future__ import annotations

import os
import pickle
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from calendarapi.calendarapi_client import CalendarapiClient
from calendarapi.configuration import Environment
from calendarapi.http.auth.oauth_2 import AuthorizationCodeAuthCredentials
from calendarapi.models.oauth_scope import OauthScope

from billable.config import get_settings

_BILLABLE_TAG = "[BILLABLE]"
_PHONE_RE = re.compile(r"phone:\s*(\+\d+)", re.IGNORECASE)


@dataclass(frozen=True)
class BillableMeeting:
    event_id: str
    title: str
    client_email: str
    client_name: str
    client_phone: str | None
    start_time: datetime
    end_time: datetime
    duration_minutes: int


def _build_client_unauthenticated() -> CalendarapiClient:
    s = get_settings()
    return CalendarapiClient(
        authorization_code_auth_credentials=AuthorizationCodeAuthCredentials(
            oauth_client_id=s.google_oauth_client_id,
            oauth_client_secret=s.google_oauth_client_secret,
            oauth_redirect_uri=s.google_oauth_redirect_uri,
            oauth_scopes=[
                OauthScope.HTTPS_WWW_GOOGLEAPIS_COM_AUTH_CALENDAR_READONLY,
            ],
        ),
        environment=Environment.PRODUCTION,
    )


def build_authenticated_client() -> CalendarapiClient:
    """Load a stored OAuth token from disk and return a ready-to-use client.

    Run `python -m billable.bootstrap_auth` once to create the token file.
    """
    s = get_settings()
    if not os.path.exists(s.google_token_file):
        raise FileNotFoundError(
            f"Google token file '{s.google_token_file}' not found. "
            "Run `python -m billable.bootstrap_auth` first."
        )

    with open(s.google_token_file, "rb") as f:
        token = pickle.load(f)

    base = _build_client_unauthenticated()
    creds = base.config.authorization_code_auth_credentials.clone_with(
        oauth_token=token
    )
    config = base.config.clone_with(authorization_code_auth_credentials=creds)
    return CalendarapiClient(config=config)


def _parse_client(event) -> tuple[str, str]:
    """Return (email, display_name) of the first non-organizer attendee, or ('','')."""
    attendees = getattr(event, "attendees", None) or []
    for a in attendees:
        if getattr(a, "organizer", False):
            continue
        email = getattr(a, "email", "") or ""
        name = getattr(a, "display_name", "") or email.split("@")[0]
        if email:
            return email, name
    return "", ""


def _parse_phone(event) -> str | None:
    desc = getattr(event, "description", None) or ""
    m = _PHONE_RE.search(desc)
    return m.group(1) if m else None


def _to_meeting(event) -> BillableMeeting | None:
    start = getattr(getattr(event, "start", None), "date_time", None)
    end = getattr(getattr(event, "end", None), "date_time", None)
    if not start or not end:
        return None

    email, name = _parse_client(event)
    duration = int((end - start).total_seconds() // 60)
    return BillableMeeting(
        event_id=event.id,
        title=getattr(event, "summary", "") or "",
        client_email=email,
        client_name=name,
        client_phone=_parse_phone(event),
        start_time=start,
        end_time=end,
        duration_minutes=duration,
    )


def get_recently_ended_meetings(
    client: CalendarapiClient,
    now: datetime | None = None,
    window_minutes: int = 2,
) -> list[BillableMeeting]:
    """Return [BILLABLE] events whose end time falls in (now - window, now]."""
    s = get_settings()
    now = now or datetime.now(timezone.utc)
    time_min = now - timedelta(minutes=window_minutes)

    result = client.events.list_events(
        s.google_calendar_id,
        time_min=time_min,
        time_max=now,
        single_events=True,
    )

    if not result.is_success():
        raise RuntimeError(f"Calendar list_events failed: {result.errors}")

    items = getattr(result.body, "items", None) or []
    meetings: list[BillableMeeting] = []
    for event in items:
        title = getattr(event, "summary", "") or ""
        if _BILLABLE_TAG not in title:
            continue
        end = getattr(getattr(event, "end", None), "date_time", None)
        if not end or end > now or end < time_min:
            continue
        m = _to_meeting(event)
        if m is not None:
            meetings.append(m)
    return meetings
