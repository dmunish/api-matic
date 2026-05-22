"""PayPal Orders — create a payable order, return the approval URL."""
from __future__ import annotations

from dataclasses import dataclass

from paypalserversdk.configuration import Environment
from paypalserversdk.http.auth.o_auth_2 import ClientCredentialsAuthCredentials
from paypalserversdk.models.amount_with_breakdown import AmountWithBreakdown
from paypalserversdk.models.checkout_payment_intent import CheckoutPaymentIntent
from paypalserversdk.models.order_request import OrderRequest
from paypalserversdk.models.purchase_unit_request import PurchaseUnitRequest
from paypalserversdk.paypal_serversdk_client import PaypalServersdkClient

from billable.config import get_settings


@dataclass(frozen=True)
class PaypalOrder:
    order_id: str
    status: str
    approve_url: str


def build_client() -> PaypalServersdkClient:
    s = get_settings()
    env = (
        Environment.SANDBOX
        if s.paypal_mode.lower() == "sandbox"
        else Environment.PRODUCTION
    )
    return PaypalServersdkClient(
        client_credentials_auth_credentials=ClientCredentialsAuthCredentials(
            o_auth_client_id=s.paypal_client_id,
            o_auth_client_secret=s.paypal_client_secret,
        ),
        environment=env,
    )


def _amount_for(duration_minutes: int, hourly_rate: float) -> str:
    return f"{round((duration_minutes / 60) * hourly_rate, 2):.2f}"


def _extract_approve_url(order) -> str:
    for link in getattr(order, "links", None) or []:
        if getattr(link, "rel", "") == "approve":
            return link.href
    raise RuntimeError("PayPal order response had no `approve` link")


def create_payment_order(
    client: PaypalServersdkClient,
    meeting_title: str,
    duration_minutes: int,
    hourly_rate: float,
    currency: str = "USD",
) -> PaypalOrder:
    """Create a PayPal Order and return its id, status, and approve URL."""
    amount = _amount_for(duration_minutes, hourly_rate)
    request = {
        "body": OrderRequest(
            intent=CheckoutPaymentIntent.CAPTURE,
            purchase_units=[
                PurchaseUnitRequest(
                    amount=AmountWithBreakdown(
                        currency_code=currency,
                        value=amount,
                    ),
                    description=meeting_title[:127] or "Consulting session",
                ),
            ],
        ),
        "prefer": "return=representation",
    }

    result = client.orders.create_order(request)
    if not result.is_success():
        raise RuntimeError(f"PayPal create_order failed: {result.errors}")

    order = result.body
    return PaypalOrder(
        order_id=order.id,
        status=order.status,
        approve_url=_extract_approve_url(order),
    )
