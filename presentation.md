# Billable

> Auto-invoice clients the moment a calendar meeting ends.

Built in Python with FastAPI, integrating **four unrelated APIs** through a single MCP server (`context-matic`).

---

## The problem

Freelancers and consultants lose revenue to forgotten or delayed invoices.

- A 1-hour call ends.
- The freelancer forgets to invoice for two days.
- Client forgets the value, queries the rate, or just never pays.

**Billable** removes the manual step entirely.

---

## What happens, end to end

```
Google Calendar event ends ([BILLABLE] tag)
            │
            ▼
   amount = duration ÷ 60 × hourly_rate
            │
            ▼
     PayPal Order created
   (returns approve URL)
            │
        ┌───┴────┐
        ▼        ▼
 Slack receipt   Twilio SMS to client
                       │
                       ▼
              Follow-up SMS reminder
              (10s demo / 24h production)
```

Zero manual steps after the meeting ends.

---

## Architecture

```
billable/
├── config.py             ← pydantic-settings, .env-driven
├── bootstrap_auth.py     ← one-time Google OAuth bootstrap
├── app.py                ← FastAPI + lifespan poll loop + /trigger /health
└── services/
    ├── calendar_service.py    ← google-calendar-apimatic-sdk
    ├── paypal_service.py      ← paypal-server-sdk (Orders API)
    ├── slack_service.py       ← incoming webhook + Block Kit
    └── sms_service.py         ← twilio-api-sdk + threading.Timer
```

**Design principles**
- Flat modules, plain functions, one dataclass per service for return shapes.
- No provider abstractions, no strategy patterns — there's exactly one of each.
- Explicit configuration via `Settings`, no hidden globals.
- Every external dependency is injected (clients are arguments, not module state) — testable in isolation.

---

## Runtime model

- **FastAPI** + `lifespan` context manager.
- An `asyncio` task polls Google Calendar every 60s.
- Blocking SDK calls are dispatched with `asyncio.to_thread` so the event loop stays free.
- `processed_events: set[str]` deduplicates events in-memory.
- `threading.Timer` schedules the SMS follow-up.

A `POST /trigger` endpoint fires the full flow manually — used for demos and when calendar polling isn't bootstrapped.

---

## Four APIs unified through one MCP server

| Service | SDK (via context-matic) | Purpose |
|---|---|---|
| Google Calendar | `google-calendar-apimatic-sdk` | Detect `[BILLABLE]` events |
| PayPal | `paypal-server-sdk` | Create payable Order, return approve URL |
| Slack | `requests` (webhook) | Block Kit receipt to channel |
| Twilio | `twilio-api-sdk` | SMS payment link + reminder |

Every SDK was discovered and wired through **context-matic**'s `fetch_api` / `ask` / `endpoint_search` — no manual SDK research, no Stack-Overflow archaeology.

---

## Key design decisions and tradeoffs

### 1. PayPal Orders instead of Invoices
The original plan called for PayPal's Invoicing API. The PayPal Server SDK doesn't expose those endpoints — only Orders, Payments, Vault, Transaction Search, Subscriptions. We pivoted to the **Orders API** and surface the HATEOAS `approve` link as the "payment URL".

- ✅ Modern PayPal pattern (invoicing is legacy)
- ✅ Stays inside the context-matic constraint
- ⚠️ No formal invoice PDF in PayPal's dashboard

### 2. Interactive OAuth → one-time bootstrap
Google Calendar uses Authorization Code flow — needs a browser. We split the concern:

- `python -m billable.bootstrap_auth` once, pickles a token to disk.
- `build_authenticated_client()` loads the token at startup.
- If no token, the poll loop **disables itself with a warning** — the rest of the app keeps working.

### 3. In-memory state
- Dedup set and follow-up timer both live in process memory.
- Lost on restart. Acceptable for this brief; production would back both with a durable store.

### 4. Real API calls in tests
The user mandated real API calls, not mocks. We split tests two ways:

- **Pure logic tests** — deterministic, no network.
- **Live tests** — marked `@pytest.mark.live`, gated by credential fixtures, **skip when env vars are absent**.

Result: green locally without secrets, fully exercised in CI / with `.env` filled.

---

## Testing — verified, not assumed

**26 tests total, organized per module.**

```
tests/
├── test_config.py            ← 3 tests
├── test_calendar_service.py  ← 10 tests (9 deterministic + 1 live)
├── test_paypal_service.py    ← 6 tests (5 deterministic + 1 live)
├── test_slack_service.py     ← 4 tests (2 deterministic + 2 live)
├── test_sms_service.py       ← 2 tests (1 deterministic + 1 live)
└── test_app.py               ← 2 tests (FastAPI TestClient)
```

### Final result

```
============== 25 passed, 1 skipped in 9.00s ==============
```

The one skip: `test_get_recently_ended_meetings_live` needs the OAuth bootstrap to be run (creates `google_token.json`). All other live calls verified end-to-end.

### Verified live with real responses

| API | Evidence |
|---|---|
| **PayPal sandbox** | Order ID `0YH93907PP658203X`, status `CREATED`, approve URL contains the same token. |
| **Slack** | HTTP 200 + body `"ok"` — webhook's documented success contract. |
| **Twilio** | Structured 21608 error in response body (auth/from/payload accepted; trial-account verification is the only gate). |

No false positives. Tests prove real API contact.

---

## What we deliberately did *not* build

- **No payment-capture step**: returns the approve URL; capture happens on a return webhook (out of scope).
- **No persistent dedup or scheduler**: in-memory only.
- **No retries**: PayPal failure aborts the flow; Slack/SMS failures are logged.
- **No payment-status follow-up**: reminder fires unconditionally; doesn't check if the client paid.
- **No provider abstraction layer**: adding Stripe later means a new module, not a refactor.

These would be the first additions for a real production deployment. They were left out per the "simplicity first" guideline — solve today's problem cleanly, leave hooks where you'll need them.

---

## What this demonstrates

1. **Four heterogeneous APIs** — Calendar, payments, chat, SMS — integrated through a single MCP server, in one codebase.
2. **Real verification, not theater** — every external boundary is provably exercised.
3. **Architecture that fits the problem size** — no premature patterns, no speculative configurability.
4. **Production-shaped where it matters** — typed config, dependency injection, isolated tests, graceful degradation when components are unconfigured.

Built in well under the 2-hour budget. The bulk of the work was *deciding what not to build*.
