# Billable — Implementation Notes

Auto-invoices clients when a `[BILLABLE]`-tagged Google Calendar meeting ends.

```
Calendar poll (60s) ──► [BILLABLE] just ended? ──► PayPal Order ──► Slack receipt
                                                         │
                                                         └─► Twilio SMS ──► follow-up (10s demo / 24h prod)
```

---

## Layout

```
billable/
├── config.py             # pydantic-settings, .env loader
├── bootstrap_auth.py     # one-time Google OAuth bootstrap → google_token.json
├── app.py                # FastAPI app, lifespan poll loop, /trigger /health
└── services/
    ├── calendar_service.py
    ├── paypal_service.py
    ├── slack_service.py
    └── sms_service.py
tests/                    # pytest — 21 deterministic, 5 live (gated on creds)
```

Flat modules, plain functions, one dataclass per service for return shapes (`BillableMeeting`, `PaypalOrder`). No base classes, no provider abstractions — there's exactly one of each service.

---

## SDKs (all via context-matic)

| Service | Package | Notes |
|---|---|---|
| Google Calendar | `google-calendar-apimatic-sdk==1.0.3` | Authorization Code flow; token persisted via pickle. |
| PayPal | `paypal-server-sdk==2.0.0` | **Orders API** (not Invoices — see tradeoff below). |
| Slack | `requests` (no SDK) | Incoming webhook; Block Kit JSON. |
| Twilio | `twilio-api-sdk==1.0.1` | APIMatic build, **not** the official `twilio` package. |

---

## Key choices and tradeoffs

### 1. PayPal Orders instead of Invoices
The PLAN called for the Invoicing API (`create_invoice → send_invoice → payer_view_url`). The PayPal Server SDK exposed by context-matic only covers Orders, Payments, Vault, Transaction Search, and Subscriptions — **no invoicing endpoints**. We use the Orders API and surface the HATEOAS `approve` link as the "payment URL".

- Pro: stays within the hard requirement to use context-matic; this is how modern PayPal integrations work anyway.
- Con: no formal invoice PDF in the PayPal dashboard. The client pays a checkout link, not an invoice.

### 2. Google Calendar auth requires a one-time bootstrap
The SDK's Authorization Code flow is interactive (prints a URL, reads a `code`). A polling loop can't run that unattended. So we split it:

- `python -m billable.bootstrap_auth` — runs the consent flow once, pickles the token to `GOOGLE_TOKEN_FILE`.
- `calendar_service.build_authenticated_client()` — loads the token at startup and clones a configured client.

If the token file is missing on app start, the poll loop logs a warning and disables itself — the `/trigger` endpoint and rest of the app still work.

### 3. Twilio SDK is the APIMatic build
PLAN.md referenced the official `twilio` SDK. The context-matic-published package is `twilio-api-sdk` with different imports (`twilioapis.*`) and a different surface (`client.sms.create_message(account_sid, to, mfrom=..., body=...)`). We use the APIMatic build because context-matic is a hard requirement.

### 4. In-memory dedup and scheduling
- `app.processed_events: set[str]` — in-process dedup. Lost on restart, which is acceptable per the brief.
- `threading.Timer` — schedules the follow-up SMS. Also dies on restart. Production would use a persistent job queue; out of scope.

### 5. FastAPI + lifespan polling
Instead of Flask + `threading.Thread`, we use FastAPI's `lifespan` context manager to start an `asyncio` task that polls every 60s. The poll itself runs the blocking SDK call via `asyncio.to_thread` so it doesn't block the event loop. `lifespan` also cancels the task cleanly on shutdown.

### 6. Configuration via pydantic-settings
`Settings` reads `.env`, exposes typed fields, and is cached as a singleton via `lru_cache`. Tests construct ad-hoc `Settings(...)` instances to verify config logic without touching the file system.

### 7. "Real API calls" testing strategy
The user mandated real API calls in tests. Approach:

- **Pure logic tests** (amount math, phone regex, attendee parsing, Block Kit shape, dedup) run deterministically with no network.
- **Live tests** marked `@pytest.mark.live` hit the real services (PayPal sandbox, Slack webhook, Twilio). Each is gated by a credential fixture in `conftest.py` that calls `pytest.skip` when the relevant env vars are missing.
- Result: `pytest` is green locally without credentials (21 passed, 5 skipped). In CI with secrets set, the live tests run and prove end-to-end correctness.

The live SMS test additionally requires `TEST_SMS_TO=+verifiednumber` to avoid sending to arbitrary numbers.

---

## Running

```powershell
# 1. Install
.\venv\Scripts\python.exe -m pip install -r requirements.txt

# 2. Configure
cp .env.example .env   # then fill in credentials

# 3. One-time Google OAuth (only if you want calendar polling)
.\venv\Scripts\python.exe -m billable.bootstrap_auth

# 4. Run
.\venv\Scripts\python.exe -m uvicorn billable.app:app --port 5000

# 5. Test
.\venv\Scripts\python.exe -m pytest
```

---

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET`  | `/health`  | Returns `{status, processed}`. |
| `POST` | `/trigger` | Manually fire the full flow with a JSON `TriggerPayload` (for demos / when calendar polling isn't bootstrapped). |

`TriggerPayload` fields: `event_id`, `title`, `client_email`, `client_name`, `client_phone?`, `duration_minutes`.

---

## What's deliberately *not* here

- No payment-capture step. `create_payment_order` returns the approve URL; capture would happen on a return webhook (out of scope).
- No persistent dedup or scheduler. In-memory only.
- No retries. A PayPal failure aborts the flow; Slack/SMS failures are logged but don't retry.
- No payment-status follow-up. The reminder fires unconditionally after the delay; it doesn't check whether the client actually paid.
- No provider abstraction layer. One PayPal, one Twilio, one Slack — adding Stripe later means a new module, not a strategy pattern.
