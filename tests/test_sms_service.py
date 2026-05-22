import threading
import time

import pytest

from billable.services import sms_service


def test_send_payment_sms_schedules_followup(monkeypatch) -> None:
    sends: list[str] = []

    def fake_send(client, to, body):
        sends.append(body)
        return "SMxxxx"

    monkeypatch.setattr(sms_service, "_send", fake_send)

    follow_up_fired = threading.Event()

    sid = sms_service.send_payment_sms(
        client=None,
        phone="+10000000000",
        client_name="Alex",
        amount=112.50,
        payment_url="https://pay/x",
        follow_up_delay=0.05,
        on_follow_up=follow_up_fired.set,
    )
    assert sid == "SMxxxx"
    assert follow_up_fired.wait(timeout=2.0)
    assert len(sends) == 2
    assert "Pay here: https://pay/x" in sends[0]
    assert "Reminder" in sends[1]


@pytest.mark.live
def test_send_payment_sms_live(twilio_settings) -> None:
    """Sends a real SMS via Twilio to TWILIO_TEST_NUMBER."""
    if not twilio_settings.twilio_test_number:
        import pytest as _pytest
        _pytest.skip("TWILIO_TEST_NUMBER not set")
    client = sms_service.build_client()
    sid = sms_service.send_payment_sms(
        client=client,
        phone=twilio_settings.twilio_test_number,
        client_name="Live Test",
        amount=1.00,
        payment_url="https://example.com/pay",
        follow_up_delay=3600,  # don't actually fire during the test
    )
    assert sid.startswith("SM")
