"""Messages to the customer about their order, sent by SMS through the outbox.

The wording is approved business content (docs/PROGRESS.md, Agent B section). Change it only
with the human's approval.

These are called inside the transaction that causes the message, so a change that is rolled
back sends nothing, and a repeat sends nothing new (one message per order and kind).
Never log the text, the phone number or the total.
"""

from apps.messaging import services as messaging

from .models import Order

PAYMENT_RECEIVED_SMS = (
    "S.K Clothing: we received your payment for order {reference} (GHS {total}). "
    "We will text you when it is on its way."
)
ORDER_RECEIVED_COD_SMS = (
    "S.K Clothing: we received order {reference} (GHS {total}). "
    "We will call you to confirm it before we pack it."
)


def _ghs(pesewas: int) -> str:
    """Whole pesewas as cedis with two decimals, with no floating point: 7500 becomes 75.00."""
    return f"{pesewas // 100}.{pesewas % 100:02d}"


def _queue(order: Order, *, template: str, wording: str) -> None:
    total = order.total_pesewas
    if not order.contact_phone or total is None:
        return
    messaging.queue_sms(
        to_e164=order.contact_phone,
        text=wording.format(reference=order.reference, total=_ghs(total)),
        template=template,
        idempotency_key=f"{template}-{order.pk}",
    )


def queue_payment_received(order: Order) -> None:
    """An online payment was verified and applied."""
    _queue(order, template="payment_received", wording=PAYMENT_RECEIVED_SMS)


def queue_order_received_cod(order: Order) -> None:
    """A pay-on-delivery order was placed; staff will phone to confirm it."""
    _queue(order, template="order_received_cod", wording=ORDER_RECEIVED_COD_SMS)
