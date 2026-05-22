"""Shared pytest fixtures and credential-gating helpers.

User mandate: tests hit REAL APIs. When credentials for an API are missing,
the corresponding tests are skipped (not faked) — keeping the suite green
locally while still proving end-to-end correctness in CI with secrets set.
"""
from __future__ import annotations

import pytest

from billable.config import Settings, get_settings


@pytest.fixture(scope="session")
def settings() -> Settings:
    get_settings.cache_clear()
    return get_settings()


def _require(*fields: str) -> Settings:
    s = get_settings()
    missing = [f for f in fields if not getattr(s, f, "")]
    if missing:
        pytest.skip(f"Missing credentials: {', '.join(missing)}")
    return s


@pytest.fixture
def paypal_settings() -> Settings:
    return _require("paypal_client_id", "paypal_client_secret")


@pytest.fixture
def slack_settings() -> Settings:
    return _require("slack_webhook_url")


@pytest.fixture
def twilio_settings() -> Settings:
    return _require("twilio_account_sid", "twilio_auth_token", "twilio_from_number")


@pytest.fixture
def calendar_settings() -> Settings:
    import os

    s = _require("google_oauth_client_id", "google_oauth_client_secret")
    if not os.path.exists(s.google_token_file):
        pytest.skip(
            f"No google token file at {s.google_token_file} — "
            "run `python -m billable.bootstrap_auth` first"
        )
    return s


