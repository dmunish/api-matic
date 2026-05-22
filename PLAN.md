# Billable — Project Plan

> Auto-invoice clients the moment a calendar meeting ends.
> Stack: Python · Google Calendar API · PayPal Server SDK · Slack API · Twilio
> Time budget: 2 hours

---

## Problem

Freelancers and agencies lose revenue to delayed or forgotten invoices. Billable watches your
Google Calendar, detects when a billable meeting ends, creates and sends a PayPal invoice, posts a
receipt to Slack, and texts the client a payment link — with zero manual action.

---

## Core Flow

```
Google Calendar (poll every 60s)
        |
        | event tagged [BILLABLE] just ended?
        v
  calculate amount
  (duration_min / 60) * HOURLY_RATE
        |
        +----------+----------+
        |                     |
        v                     v
 PayPal invoice          (on success)
 create + send               |
        |          +---------+---------+
        |          |                   |
        v          v                   v
   payment URL   Slack post        Twilio SMS
                (receipt)       (payment link)
                                       |
                              24h follow-up timer
                              (10s in demo mode)
```

---

## Project Structure

```
Billable/
├── .env                    # credentials — never committed
├── .env.example            # template for .env
├── requirements.txt
├── config.py               # reads env vars, defines HOURLY_RATE
├── app.py                  # Flask app, polling loop, /trigger endpoint
├── services/
│   ├── __init__.py
│   ├── calendar_service.py # Google Calendar polling + event parsing
│   ├── paypal_service.py   # invoice create + send
│   ├── slack_service.py    # Block Kit receipt message
│   └── sms_service.py      # Twilio send + follow-up timer
└── PLAN.md
```

---

## Environment Variables

```env
# Google Calendar
GOOGLE_CALENDAR_ID=primary
GOOGLE_CREDENTIALS_JSON=path/to/credentials.json
GOOGLE_TOKEN_JSON=path/to/token.json

# PayPal
PAYPAL_CLIENT_ID=
PAYPAL_CLIENT_SECRET=
PAYPAL_MODE=sandbox           # sandbox | live

# Slack
SLACK_WEBHOOK_URL=

# Twilio
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_FROM_NUMBER=+1XXXXXXXXXX

# App config
HOURLY_RATE=150
YOUR_NAME=Your Name
YOUR_EMAIL=you@example.com
DEMO_MODE=true                # true = follow-up fires in 10s instead of 24h
```

---

## Dependencies

```
flask
google-api-python-client
google-auth-httplib2
google-auth-oauthlib
paypalserversdk
slack_sdk
twilio
python-dotenv
```

Install:
```bash
pip install flask google-api-python-client google-auth-httplib2 \
  google-auth-oauthlib paypalserversdk slack_sdk twilio python-dotenv
```

---

## Implementation Plan

### Phase 1 — Scaffold (0:00 – 0:15)

- [ ] Create project directory and folder structure above
- [ ] Create `.env` from template, fill all credentials
- [ ] Write `config.py` — load env vars, expose constants
- [ ] Write bare `app.py` — Flask app boots with `flask run`
- [ ] Smoke test: `python app.py` runs without errors

**config.py sketch:**
```python
import os
from dotenv import load_dotenv

load_dotenv()

HOURLY_RATE        = float(os.getenv("HOURLY_RATE", 150))
YOUR_NAME          = os.getenv("YOUR_NAME")
YOUR_EMAIL         = os.getenv("YOUR_EMAIL")
DEMO_MODE          = os.getenv("DEMO_MODE", "true").lower() == "true"
FOLLOW_UP_DELAY    = 10 if DEMO_MODE else 86400  # seconds
```

---

### Phase 2 — Calendar Service (0:15 – 0:40)

File: `services/calendar_service.py`

**Goal:** Return a list of billable events that ended in the last 2 minutes, not seen before.

```python
def get_recently_ended_meetings() -> list[dict]:
    """
    Returns events where:
      - title contains [BILLABLE]
      - end time is between (now - 2min) and now
    Each dict: {
        event_id, title, client_email,
        client_name, client_phone,
        start_time, end_time, duration_minutes
    }
    Phone parsed from description if present: 'phone: +XXXXXXXXXXX'
    """
```

- Use `service.events().list()` with `timeMin` and `timeMax` set to a 2-minute window
- Filter by `[BILLABLE]` in `summary`
- Parse first non-organizer attendee as client
- Parse phone from `description` field with regex: `phone:\s*(\+\d+)`

**Test:** Create a Google Calendar event:
```
Title:       [BILLABLE] Strategy Session
Attendees:   client@example.com
Description: phone: +923001234567
Duration:    ending 1 minute ago
```
Run the function and assert it returns the event with correct fields.

---

### Phase 3 — PayPal Service (0:40 – 1:00)

File: `services/paypal_service.py`

**Goal:** Create a PayPal draft invoice, send it, return the payment URL.

```python
def create_and_send_invoice(
    client_email: str,
    meeting_title: str,
    duration_minutes: int,
    hourly_rate: float
) -> str:
    """
    Creates and sends a PayPal invoice.
    Returns payer_view_url (the payment link).
    """
```

Steps inside the function:
1. Calculate `amount = round((duration_minutes / 60) * hourly_rate, 2)`
2. Build invoice payload with line item: `meeting_title`, `amount`, currency `USD`
3. Call `invoices.create_invoice()` → get `invoice_id`
4. Call `invoices.send_invoice(invoice_id)` → status becomes `SENT`
5. Call `invoices.get_invoice(invoice_id)` → extract `detail.metadata.payer_view_url`
6. Return the URL

**Test:** Call the function with dummy args against sandbox. Verify invoice appears in
PayPal sandbox dashboard and the returned URL is a valid HTTPS link.

---

### Phase 4 — Slack Service (1:00 – 1:15)

File: `services/slack_service.py`

**Goal:** Post a Block Kit receipt to the configured Slack webhook.

```python
def post_receipt(
    meeting_title: str,
    client_email: str,
    amount: float,
    duration_minutes: int,
    payment_url: str
) -> None:

def post_followup_sent(client_email: str) -> None:
    # Separate message noting the 24h follow-up fired
```

Block Kit layout for `post_receipt`:
```
┌─────────────────────────────────┐
│ 💰 Invoice sent                  │
│                                 │
│ Strategy Session                │
│ Client: client@example.com      │
│ Duration: 45 min  Amount: $112.50│
│                                 │
│ [View Invoice →]                │
└─────────────────────────────────┘
```

**Test:** Call the function directly. Verify the message appears in Slack with correct
values and the button link points to the PayPal URL.

---

### Phase 5 — SMS Service (1:15 – 1:30)

File: `services/sms_service.py`

**Goal:** Send payment SMS immediately, schedule a follow-up.

```python
def send_payment_sms(
    phone: str,
    client_name: str,
    amount: float,
    payment_url: str
) -> None:
    """
    Sends initial SMS then schedules follow-up via threading.Timer.
    Delay = 10s in DEMO_MODE, 86400s (24h) in production.
    """
```

Initial SMS body:
```
Hi {client_name}, your invoice for ${amount} is ready.
Pay here: {payment_url}
```

Follow-up SMS body:
```
Reminder: your invoice for ${amount} is still outstanding.
Pay here: {payment_url}
```

Note: wrap `client.messages.create()` in try/except — if no phone was parsed from the
calendar event, skip silently and log a warning.

**Test:** Send to your own number. Verify initial SMS arrives. Wait 10 seconds
(DEMO_MODE=true). Verify follow-up arrives.

---

### Phase 6 — Wire Everything Together (1:30 – 1:50)

File: `app.py`

```python
import threading, time
from flask import Flask, jsonify, request
from services.calendar_service import get_recently_ended_meetings
from services.paypal_service import create_and_send_invoice
from services.slack_service import post_receipt, post_followup_sent
from services.sms_service import send_payment_sms
from config import HOURLY_RATE

app = Flask(__name__)
processed_events = set()  # in-memory dedup store

def handle_meeting(meeting: dict):
    event_id = meeting["event_id"]
    if event_id in processed_events:
        return
    processed_events.add(event_id)

    amount = round((meeting["duration_minutes"] / 60) * HOURLY_RATE, 2)

    try:
        payment_url = create_and_send_invoice(
            meeting["client_email"],
            meeting["title"],
            meeting["duration_minutes"],
            HOURLY_RATE
        )
    except Exception as e:
        print(f"[ERROR] PayPal failed for {event_id}: {e}")
        return  # do not fire Slack/SMS if invoice failed

    post_receipt(
        meeting["title"],
        meeting["client_email"],
        amount,
        meeting["duration_minutes"],
        payment_url
    )

    if meeting.get("client_phone"):
        send_payment_sms(
            meeting["client_phone"],
            meeting.get("client_name", "there"),
            amount,
            payment_url
        )

def poll_loop():
    while True:
        meetings = get_recently_ended_meetings()
        for m in meetings:
            handle_meeting(m)
        time.sleep(60)

@app.route("/trigger", methods=["POST"])
def trigger():
    """Manual trigger for demo — accepts mock event payload."""
    meeting = request.json
    handle_meeting(meeting)
    return jsonify({"status": "triggered"})

@app.route("/health")
def health():
    return jsonify({"status": "ok", "processed": len(processed_events)})

if __name__ == "__main__":
    t = threading.Thread(target=poll_loop, daemon=True)
    t.start()
    app.run(debug=True, port=5000)
```

**End-to-end test:** Create a real `[BILLABLE]` calendar event ending in 2 minutes.
Watch the terminal. Verify: invoice created → Slack message → SMS → follow-up SMS (10s later).

---

### Phase 7 — Demo Prep (1:50 – 2:00)

- [ ] Pre-create a fallback invoice in PayPal sandbox — save its URL in case live demo fails
- [ ] Open 3 windows side by side: terminal logs, Slack channel, phone
- [ ] Prepare `/trigger` Postman request with this body:

```json
{
  "event_id": "demo-001",
  "title": "[BILLABLE] Strategy Session",
  "client_email": "client@example.com",
  "client_name": "Alex",
  "client_phone": "+923001234567",
  "duration_minutes": 45
}
```

- [ ] Rehearse the 90-second pitch (see below)

---

## Demo Script (90 seconds)

> "Freelancers lose thousands a year to forgotten invoices.
> I just finished a 45-minute client call. Watch what happens."

→ Calendar event ends (or hit `/trigger` in Postman)

> "Billable detects the meeting ended, calculates the fee — $112.50 for 45 minutes —
> and creates a PayPal invoice automatically."

→ Point to Slack message appearing live

> "The client gets a text with the payment link before they've closed their laptop."

→ Hold up phone showing SMS

> "And if they haven't paid in 24 hours..."

→ Wait 10 seconds for follow-up SMS

> "...they get a reminder. Zero manual work. Four completely unrelated APIs unified in
> under 2 hours using APIMatic Context-Matic."

---

## Acceptance Criteria Summary

| ID | Area | Priority |
|----|------|----------|
| AC-01 | Detect [BILLABLE] events within 2 min of ending | must |
| AC-02 | Non-tagged events are ignored | must |
| AC-03 | Each event processed exactly once | must |
| AC-04 | Amount = round((duration / 60) * rate, 2) | must |
| AC-05 | Invoice status is SENT, payment URL returned | must |
| AC-06 | PayPal failure blocks Slack + SMS | should |
| AC-07 | Slack message contains all required fields + link | must |
| AC-08 | Follow-up triggers a second Slack post | should |
| AC-09 | SMS sent when phone number present in event | must |
| AC-10 | Missing phone skips SMS, rest of flow continues | must |
| AC-11 | Follow-up SMS fires after delay | should |
| AC-12 | Full flow runs without manual intervention | must |
| AC-13 | /trigger endpoint fires full flow from mock payload | must |
| AC-14 | Single API failure does not crash remaining steps | nice |

---

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| PayPal sandbox slow or down | Pre-create one invoice, save URL as `FALLBACK_URL` in `.env` |
| Calendar OAuth token expires | Pre-authorize and test token the night before |
| SMS doesn't arrive on stage | Show Twilio dashboard message logs instead |
| Calendar event timing off | Use `/trigger` endpoint — don't rely on real event timing for demo |
| Duplicate invoices in demo | `processed_events` set deduplicates; clear it between test runs |

---

## What to Mention But Not Build

These are verbal pitch points — skip implementation to stay in budget:

- **Stripe / Adyen support** — swap PayPal for any payment processor
- **Splitit integration** — offer installment plans for large invoices
- **Calendar auto-tagging** — NLP to detect client meetings and add `[BILLABLE]` automatically
- **Dashboard** — simple web UI showing all invoices and payment status

---

*Industry: FinTech — billing and payment automation for professional services*
