"""Streamlit control panel for Billable.

Run with:
    streamlit run streamlit_app.py

Assumes the FastAPI backend is reachable at API_BASE (default http://localhost:5000).
"""
from __future__ import annotations

import subprocess
import sys
import uuid
from pathlib import Path

import requests
import streamlit as st

API_BASE = "http://localhost:5000"
PROJECT_ROOT = Path(__file__).parent

st.set_page_config(page_title="Billable", page_icon="💰", layout="wide")

st.title("💰 Billable")
st.caption("Auto-invoice clients when a calendar meeting ends.")

# ---------------------------------------------------------------- sidebar: health
with st.sidebar:
    st.subheader("Backend")
    st.code(API_BASE, language="text")
    if st.button("Check /health", use_container_width=True):
        try:
            r = requests.get(f"{API_BASE}/health", timeout=3)
            r.raise_for_status()
            data = r.json()
            st.success(f"OK — {data['processed']} processed")
            st.json(data)
        except requests.exceptions.RequestException as e:
            st.error(f"Unreachable: {e}")

    st.divider()
    st.subheader("About")
    st.markdown(
        "Trigger the full PayPal + Slack + Twilio flow with a mock meeting, "
        "or run the test suite — all from here."
    )

# ---------------------------------------------------------------- tabs
trigger_tab, tests_tab = st.tabs(["🚀 Trigger flow", "🧪 Run tests"])

# ---------------------------------------------------------------- trigger
with trigger_tab:
    st.subheader("Manually trigger an invoice")
    st.caption(
        "Sends a mock meeting payload to `/trigger`. The backend will create a "
        "PayPal order, post to Slack, and send an SMS if a phone number is given."
    )

    with st.form("trigger_form", clear_on_submit=False):
        col1, col2 = st.columns(2)
        with col1:
            event_id = st.text_input(
                "Event ID",
                value=f"demo-{uuid.uuid4().hex[:6]}",
                help="Unique per meeting. Same ID twice is deduped.",
            )
            title = st.text_input("Meeting title", value="[BILLABLE] Strategy Session")
            client_name = st.text_input("Client name", value="Alex")
        with col2:
            client_email = st.text_input(
                "Client email", value="danish.munib@example.com"
            )
            client_phone = st.text_input(
                "Client phone (optional)",
                value="",
                placeholder="+1XXXXXXXXXX",
            )
            duration = st.number_input(
                "Duration (minutes)", min_value=1, max_value=480, value=45, step=5
            )

        submitted = st.form_submit_button("Fire trigger", type="primary", use_container_width=True)

    if submitted:
        payload = {
            "event_id": event_id,
            "title": title,
            "client_email": client_email,
            "client_name": client_name,
            "client_phone": client_phone or None,
            "duration_minutes": int(duration),
        }
        with st.spinner("Calling backend…"):
            try:
                r = requests.post(f"{API_BASE}/trigger", json=payload, timeout=30)
                if r.status_code == 200:
                    result = r.json()
                    if result.get("status") == "processed":
                        st.success("Invoice processed ✅")
                        c1, c2, c3 = st.columns(3)
                        c1.metric("Amount", f"${result['amount']:.2f}")
                        c2.metric("PayPal Order", result["paypal_order_id"])
                        c3.metric("SMS SID", result.get("sms_sid") or "—")
                        st.link_button("Open PayPal approve URL", result["approve_url"])
                    else:
                        st.warning(f"Already processed: {result['event_id']}")
                    with st.expander("Raw response"):
                        st.json(result)
                else:
                    st.error(f"HTTP {r.status_code}: {r.text}")
            except requests.exceptions.RequestException as e:
                st.error(f"Request failed: {e}")

# ---------------------------------------------------------------- tests
with tests_tab:
    st.subheader("Run the test suite")
    st.caption("Executes `pytest` against the project. Live tests skip if creds absent.")

    col1, col2 = st.columns([1, 1])
    target = col1.selectbox(
        "Scope",
        ["All tests", "PayPal", "Slack", "Twilio", "Calendar", "Config", "App"],
    )
    verbose = col2.toggle("Verbose (-v)", value=True)

    if st.button("Run pytest", type="primary", use_container_width=True):
        target_map = {
            "All tests": "tests",
            "PayPal": "tests/test_paypal_service.py",
            "Slack": "tests/test_slack_service.py",
            "Twilio": "tests/test_sms_service.py",
            "Calendar": "tests/test_calendar_service.py",
            "Config": "tests/test_config.py",
            "App": "tests/test_app.py",
        }
        cmd = [sys.executable, "-m", "pytest", target_map[target]]
        if verbose:
            cmd.append("-v")

        with st.spinner(f"Running {' '.join(cmd[2:])}…"):
            result = subprocess.run(
                cmd, capture_output=True, text=True, cwd=PROJECT_ROOT
            )

        if result.returncode == 0:
            st.success(f"All tests passed (exit {result.returncode})")
        else:
            st.error(f"Tests failed (exit {result.returncode})")

        st.code(result.stdout or "(no stdout)", language="text")
        if result.stderr.strip():
            with st.expander("stderr"):
                st.code(result.stderr, language="text")
