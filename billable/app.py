"""FastAPI entrypoint — polls calendar, processes [BILLABLE] events end-to-end."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from dataclasses import asdict

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from billable.config import get_settings
from billable.services import paypal_service, sms_service
from billable.services.calendar_service import (
    BillableMeeting,
    build_authenticated_client,
    get_recently_ended_meetings,
)
from billable.services.slack_service import post_followup_sent, post_receipt

logger = logging.getLogger("billable")

POLL_INTERVAL_SECONDS = 60

processed_events: set[str] = set()


class TriggerPayload(BaseModel):
    event_id: str
    title: str
    client_email: str
    client_name: str = "there"
    client_phone: str | None = None
    duration_minutes: int


def handle_meeting(meeting: BillableMeeting | dict) -> dict:
    """Run the full invoice flow for a single meeting. Idempotent on event_id."""
    if isinstance(meeting, dict):
        event_id = meeting["event_id"]
        title = meeting["title"]
        client_email = meeting["client_email"]
        client_name = meeting.get("client_name") or "there"
        client_phone = meeting.get("client_phone")
        duration_minutes = meeting["duration_minutes"]
    else:
        event_id = meeting.event_id
        title = meeting.title
        client_email = meeting.client_email
        client_name = meeting.client_name or "there"
        client_phone = meeting.client_phone
        duration_minutes = meeting.duration_minutes

    if event_id in processed_events:
        return {"event_id": event_id, "status": "already_processed"}
    processed_events.add(event_id)

    s = get_settings()
    amount = round((duration_minutes / 60) * s.hourly_rate, 2)

    paypal_client = paypal_service.build_client()
    order = paypal_service.create_payment_order(
        paypal_client, title, duration_minutes, s.hourly_rate
    )

    post_receipt(title, client_email, amount, duration_minutes, order.approve_url)

    sms_sid: str | None = None
    if client_phone:
        twilio = sms_service.build_client()
        sms_sid = sms_service.send_payment_sms(
            twilio,
            client_phone,
            client_name,
            amount,
            order.approve_url,
            on_follow_up=lambda: post_followup_sent(client_email),
        )

    return {
        "event_id": event_id,
        "status": "processed",
        "amount": amount,
        "paypal_order_id": order.order_id,
        "approve_url": order.approve_url,
        "sms_sid": sms_sid,
    }


async def _poll_loop() -> None:
    """Background task that polls Google Calendar every POLL_INTERVAL_SECONDS."""
    try:
        client = build_authenticated_client()
    except FileNotFoundError as e:
        logger.warning("Calendar polling disabled: %s", e)
        return

    while True:
        try:
            meetings = await asyncio.to_thread(get_recently_ended_meetings, client)
            for m in meetings:
                try:
                    await asyncio.to_thread(handle_meeting, m)
                except Exception:
                    logger.exception("Failed to handle meeting %s", m.event_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Calendar poll failed")
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_poll_loop())
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass


app = FastAPI(title="Billable", lifespan=lifespan)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "processed": len(processed_events)}


@app.post("/trigger")
def trigger(payload: TriggerPayload) -> dict:
    try:
        return handle_meeting(payload.model_dump())
    except Exception as e:
        logger.exception("Trigger failed")
        raise HTTPException(status_code=500, detail=str(e))
