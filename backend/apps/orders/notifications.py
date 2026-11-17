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


# --- Added messages: DRAFT wording, needs the human's approval (open question 18). ---
# These have no `total` in the text or may not have one yet, so they use _queue_plain
# instead of _queue (which skips orders without a total).

AWAITING_QUOTE_SMS = (
    "S.K Clothing: we received order {reference}. "
    "We are working out your delivery fee and will text you the total."
)
CANCELLED_UNPAID_SMS = (
    "S.K Clothing: order {reference} was cancelled because it was not paid in time. "
    "You can order again anytime."
)
REFUND_STARTED_SMS = (
    "S.K Clothing: we started a refund of GHS {amount} for order {reference}. "
    "It can take a few days to reach you."
)
REFUND_MANUAL_SMS = (
    "S.K Clothing: your refund for order {reference} is being handled by our team. "
    "We will contact you soon."
)


def _queue_plain(order: Order, *, template: str, wording: str, key: str, **values: str) -> None:
    if not order.contact_phone:
        return
    messaging.queue_sms(
        to_e164=order.contact_phone,
        text=wording.format(reference=order.reference, **values),
        template=template,
        idempotency_key=key,
    )


def queue_awaiting_quote(order: Order) -> None:
    """An order was placed and the delivery fee is still being worked out."""
    _queue_plain(
        order,
        template="awaiting_quote",
        wording=AWAITING_QUOTE_SMS,
        key=f"awaiting_quote-{order.pk}",
    )


def queue_cancelled_unpaid(order: Order) -> None:
    """The grace period ended without payment and the order was cancelled."""
    _queue_plain(
        order,
        template="cancelled_unpaid",
        wording=CANCELLED_UNPAID_SMS,
        key=f"cancelled_unpaid-{order.pk}",
    )


def queue_refund_started(order: Order, *, refund_id: object, amount_pesewas: int) -> None:
    """A refund was sent to Paystack. One message per refund, not per order."""
    _queue_plain(
        order,
        template="refund_started",
        wording=REFUND_STARTED_SMS,
        key=f"refund_started-{refund_id}",
        amount=_ghs(amount_pesewas),
    )


def queue_refund_manual(order: Order, *, refund_id: object) -> None:
    """A refund could not be sent automatically and a person is handling it."""
    _queue_plain(
        order,
        template="refund_manual",
        wording=REFUND_MANUAL_SMS,
        key=f"refund_manual-{refund_id}",
    )


# --- Delivery code SMS: DRAFT wording, needs the human's approval (open question 18). ---
# The text contains the code itself. Never log the text, the code or the phone number.

DELIVERY_CODE_SMS = (
    "S.K Clothing: your delivery code for order {reference} is {code}. "
    "Give it to the rider only when you have your items."
)


def queue_delivery_code(order: Order, *, code: str, issue_number: object) -> None:
    """Send the delivery code. Call it with what issue_delivery_code or
    reissue_delivery_code returned, inside the same transaction.

    One message per issue of the code: a reissue after a lock or a lost code has a new
    issue_number, so it sends a new message, while a repeat of the same issue sends nothing.
    """
    _queue_plain(
        order,
        template="delivery_code",
        wording=DELIVERY_CODE_SMS,
        key=f"delivery_code-{order.pk}-{issue_number}",
        code=code,
    )
