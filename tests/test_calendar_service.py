from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from billable.services import calendar_service
from billable.services.calendar_service import (
    _parse_client,
    _parse_phone,
    _to_meeting,
    get_recently_ended_meetings,
)


def _evt(**kwargs) -> SimpleNamespace:
    return SimpleNamespace(**kwargs)


def test_parse_phone_extracts_when_present() -> None:
    event = _evt(description="phone: +923001234567\nNotes: ...")
    assert _parse_phone(event) == "+923001234567"


def test_parse_phone_returns_none_when_missing() -> None:
    assert _parse_phone(_evt(description="no phone here")) is None
    assert _parse_phone(_evt(description=None)) is None


def test_parse_client_picks_first_non_organizer_attendee() -> None:
    event = _evt(
        attendees=[
            SimpleNamespace(email="me@me.com", display_name="Me", organizer=True),
            SimpleNamespace(email="c@x.com", display_name="Client", organizer=False),
        ]
    )
    assert _parse_client(event) == ("c@x.com", "Client")


def test_parse_client_falls_back_to_email_prefix_for_name() -> None:
    event = _evt(
        attendees=[
            SimpleNamespace(email="alex@example.com", display_name="", organizer=False),
        ]
    )
    assert _parse_client(event) == ("alex@example.com", "alex")


def test_parse_client_handles_no_attendees() -> None:
    assert _parse_client(_evt(attendees=None)) == ("", "")


def test_to_meeting_computes_duration_in_minutes() -> None:
    start = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
    end = start + timedelta(minutes=45)
    event = _evt(
        id="evt-1",
        summary="[BILLABLE] Strategy",
        start=SimpleNamespace(date_time=start),
        end=SimpleNamespace(date_time=end),
        description="phone: +1234567890",
        attendees=[
            SimpleNamespace(email="c@x.com", display_name="C", organizer=False),
        ],
    )
    m = _to_meeting(event)
    assert m is not None
    assert m.duration_minutes == 45
    assert m.client_phone == "+1234567890"
    assert m.client_email == "c@x.com"


def test_to_meeting_returns_none_when_times_missing() -> None:
    event = _evt(
        id="x",
        summary="t",
        start=SimpleNamespace(date_time=None),
        end=SimpleNamespace(date_time=None),
        description=None,
        attendees=None,
    )
    assert _to_meeting(event) is None


def _fake_client_returning(items: list) -> SimpleNamespace:
    return SimpleNamespace(
        events=SimpleNamespace(
            list_events=lambda *a, **k: SimpleNamespace(
                is_success=lambda: True,
                body=SimpleNamespace(items=items),
            )
        )
    )


def test_get_recently_ended_meetings_filters_by_tag_and_window() -> None:
    now = datetime(2026, 5, 22, 12, 0, tzinfo=timezone.utc)
    just_ended = now - timedelta(seconds=30)
    too_old = now - timedelta(minutes=10)

    items = [
        _evt(
            id="billable-recent",
            summary="[BILLABLE] Strategy",
            start=SimpleNamespace(date_time=just_ended - timedelta(minutes=30)),
            end=SimpleNamespace(date_time=just_ended),
            description="phone: +123",
            attendees=[SimpleNamespace(email="c@x.com", display_name="C", organizer=False)],
        ),
        _evt(
            id="not-billable",
            summary="1:1 with Manager",
            start=SimpleNamespace(date_time=just_ended - timedelta(minutes=30)),
            end=SimpleNamespace(date_time=just_ended),
            description="",
            attendees=[],
        ),
        _evt(
            id="billable-too-old",
            summary="[BILLABLE] Old",
            start=SimpleNamespace(date_time=too_old - timedelta(minutes=30)),
            end=SimpleNamespace(date_time=too_old),
            description="",
            attendees=[],
        ),
    ]
    result = get_recently_ended_meetings(_fake_client_returning(items), now=now)
    assert [m.event_id for m in result] == ["billable-recent"]


@pytest.mark.live
def test_get_recently_ended_meetings_live(calendar_settings) -> None:
    """Hit the real Google Calendar API. Skipped without credentials/token."""
    client = calendar_service.build_authenticated_client()
    meetings = get_recently_ended_meetings(client, window_minutes=60 * 24 * 7)
    assert isinstance(meetings, list)
