from unittest.mock import patch

from fastapi.testclient import TestClient

from billable import app as app_module
from billable.app import app


def test_health_returns_ok() -> None:
    with TestClient(app) as client:
        # FastAPI lifespan tries to start the poll loop; that's fine — it
        # disables itself cleanly when no google token file exists.
        r = client.get("/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert "processed" in body


def test_trigger_dedupes_repeat_event_ids(monkeypatch) -> None:
    app_module.processed_events.clear()

    fake_order = type(
        "O",
        (),
        {"order_id": "ORDER-1", "status": "CREATED", "approve_url": "https://pay/x"},
    )
    with patch("billable.app.paypal_service.build_client", return_value=None), \
         patch("billable.app.paypal_service.create_payment_order", return_value=fake_order), \
         patch("billable.app.post_receipt"):
        with TestClient(app) as client:
            payload = {
                "event_id": "dup-1",
                "title": "[BILLABLE] Test",
                "client_email": "danish.munib@example.com",
                "client_name": "Alex",
                "duration_minutes": 60,
            }
            r1 = client.post("/trigger", json=payload).json()
            r2 = client.post("/trigger", json=payload).json()

    assert r1["status"] == "processed"
    assert r1["amount"] == 150.0
    assert r1["approve_url"] == "https://pay/x"
    assert r2["status"] == "already_processed"
