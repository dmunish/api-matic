import pytest

from billable.services import paypal_service
from billable.services.paypal_service import _amount_for, _extract_approve_url


def test_amount_for_one_hour_at_150() -> None:
    assert _amount_for(60, 150.0) == "150.00"


def test_amount_for_partial_hour_rounds_to_two_decimals() -> None:
    assert _amount_for(45, 150.0) == "112.50"


def test_amount_for_zero_minutes_is_zero() -> None:
    assert _amount_for(0, 150.0) == "0.00"


def test_extract_approve_url_finds_link_with_rel_approve() -> None:
    class L:
        def __init__(self, rel: str, href: str) -> None:
            self.rel = rel
            self.href = href

    order = type("O", (), {"links": [L("self", "x"), L("approve", "https://paypal/approve")]})
    assert _extract_approve_url(order) == "https://paypal/approve"


def test_extract_approve_url_raises_when_missing() -> None:
    order = type("O", (), {"links": []})
    with pytest.raises(RuntimeError):
        _extract_approve_url(order)


@pytest.mark.live
def test_create_payment_order_live(paypal_settings) -> None:
    """Hit PayPal sandbox to create a real Order and assert the approve URL."""
    client = paypal_service.build_client()
    order = paypal_service.create_payment_order(
        client,
        meeting_title="[BILLABLE] Test Session",
        duration_minutes=45,
        hourly_rate=paypal_settings.hourly_rate,
    )
    assert order.order_id
    assert order.approve_url.startswith("https://")
    assert order.status in {"CREATED", "PAYER_ACTION_REQUIRED"}
