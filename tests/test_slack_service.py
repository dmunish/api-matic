import pytest

from billable.services import slack_service
from billable.services.slack_service import _receipt_blocks


def test_receipt_blocks_include_amount_and_link() -> None:
    blocks = _receipt_blocks(
        "[BILLABLE] Strategy", "c@x.com", 112.50, 45, "https://pay/abc"
    )
    text = str(blocks)
    assert "$112.50" in text
    assert "c@x.com" in text
    assert "45 min" in text
    assert "https://pay/abc" in text


def test_receipt_blocks_has_button_with_payment_url() -> None:
    blocks = _receipt_blocks("t", "c@x.com", 1.0, 1, "https://pay/x")
    actions = [b for b in blocks if b["type"] == "actions"][0]
    assert actions["elements"][0]["url"] == "https://pay/x"


@pytest.mark.live
def test_post_receipt_live(slack_settings) -> None:
    """Posts an actual receipt to the configured Slack webhook."""
    slack_service.post_receipt(
        meeting_title="[BILLABLE] Live Test",
        client_email="danish.munib@example.com",
        amount=112.50,
        duration_minutes=45,
        payment_url="https://example.com/pay",
    )


@pytest.mark.live
def test_post_followup_sent_live(slack_settings) -> None:
    slack_service.post_followup_sent("danish.munib@example.com")
