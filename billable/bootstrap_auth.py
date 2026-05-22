"""One-time OAuth bootstrap for Google Calendar.

Usage: python -m billable.bootstrap_auth

Prints an authorization URL, prompts for the redirected `code`, exchanges it for
a token, and persists the token to GOOGLE_TOKEN_FILE for the polling loop.
"""
from __future__ import annotations

import pickle
import sys

from billable.config import get_settings
from billable.services.calendar_service import _build_client_unauthenticated


def main() -> None:
    s = get_settings()
    if not s.google_oauth_client_id or not s.google_oauth_client_secret:
        print("Google OAuth credentials missing in .env", file=sys.stderr)
        sys.exit(1)

    client = _build_client_unauthenticated()
    auth_url = client.oauth_2.get_authorization_url()
    print("1. Open this URL and authorize the app:\n")
    print(auth_url)
    print()
    code = input("2. Paste the `code` query param from the redirect URL: ").strip()
    token = client.oauth_2.fetch_token(code)

    with open(s.google_token_file, "wb") as f:
        pickle.dump(token, f)

    print(f"Token saved to {s.google_token_file}")


if __name__ == "__main__":
    main()
