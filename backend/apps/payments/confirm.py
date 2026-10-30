"""Starting a payment and confirming it. The only place that decides an order has been paid.

Rules:
- The amount sent to Paystack is the order total, read from the order. A client never names it.
- Nothing marks an order paid except `transaction/verify` saying `success` with exactly the
  attempt's amount and currency. The webhook body and the page a customer returns to are only
  hints to go and ask.
- Confirming is safe to repeat and to run at the same moment from a webhook and a return page.
  The verify call is made with no database transaction open; the result is applied under a lock
  on the attempt, so the same payment can never be applied twice.
- Money that arrives for an order that was already paid is never lost: the attempt is marked
  `duplicate` and an error is logged, so a person can refund it.

Never log an email address.
"""

import logging
import secrets
from dataclasses import dataclass

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.orders import settlement
from apps.orders.settlement import NotPayable, OrderNotFound

from .client import PaystackClient, PaystackError
from .models import PaymentAttempt

logger = logging.getLogger(__name__)

DEFAULT_LIMITS: dict[str, int | str] = {
    "attempts_per_order": 5,
    "start_ip_rate": "20/hour",
    "verify_ip_rate": "60/hour",
}

UNKNOWN_REFERENCE = "unknown_reference"
PAID = settlement.PAID
PAID_NOT_FULFILLABLE = settlement.PAID_NOT_FULFILLABLE
PAID_ORDER_CLOSED = settlement.PAID_ORDER_CLOSED
ALREADY_CONFIRMED = "already_confirmed"
FAILED = "failed"
STILL_PENDING = "pending"
MISMATCH = "mismatch"
DUPLICATE = "duplicate"

FINAL = (
    PaymentAttempt.Status.SUCCESS,
    PaymentAttempt.Status.MISMATCH,
    PaymentAttempt.Status.DUPLICATE,
)


def limit(name: str) -> int | str:
    return getattr(settings, "PAYMENT_LIMITS", {}).get(name, DEFAULT_LIMITS[name])


class TooManyAttempts(Exception):
    pass


@dataclass(frozen=True)
class StartResult:
    authorization_url: str
    reference: str


@dataclass(frozen=True)
class ConfirmResult:
    outcome: str
    order_id: int | None = None


def start_payment(
    order_reference: str, email: str, *, client: PaystackClient, callback_url: str | None = None
) -> StartResult:
    """Begin paying for an order. Raises OrderNotFound, NotPayable, TooManyAttempts, or
    PaystackError (the attempt is then marked failed and the customer may try again)."""
    order = settlement.payable_order(order_reference)
    if PaymentAttempt.objects.filter(order_id=order.order_id).count() >= int(
        limit("attempts_per_order")
    ):
        raise TooManyAttempts
    reference = f"{order.reference}-{secrets.token_hex(4)}"
    attempt = PaymentAttempt.objects.create(
        order_id=order.order_id,
        reference=reference,
        amount_pesewas=order.total_pesewas,
        payer_email=email,
    )
    try:
        result = client.initialize(
            email=email,
            amount_pesewas=order.total_pesewas,
            reference=reference,
            callback_url=callback_url,
        )
    except PaystackError:
        attempt.status = PaymentAttempt.Status.FAILED
        attempt.save(update_fields=["status"])
        raise
    return StartResult(result.authorization_url, reference)


def confirm_reference(reference: str, *, client: PaystackClient) -> ConfirmResult:
    """Ask Paystack what happened to this payment and apply the answer, once.

    Raises PaystackError if Paystack cannot be asked; nothing has changed and the caller should
    ask again later (a webhook answers 503 so Paystack sends it again).
    """
    attempt = PaymentAttempt.objects.filter(reference=reference).first()
    if attempt is None:
        return ConfirmResult(UNKNOWN_REFERENCE)
    if attempt.status in FINAL:
        return ConfirmResult(ALREADY_CONFIRMED, attempt.order_id)

    answer = client.verify(reference)  # no transaction is open while we wait for Paystack

    with transaction.atomic():
        attempt = PaymentAttempt.objects.select_for_update().get(pk=attempt.pk)
        if attempt.status in FINAL:
            return ConfirmResult(ALREADY_CONFIRMED, attempt.order_id)
        if answer.status == "failed":
            attempt.status = PaymentAttempt.Status.FAILED
            attempt.save(update_fields=["status"])
            settlement.mark_payment_failed(attempt.order_id)
            return ConfirmResult(FAILED, attempt.order_id)
        if answer.status != "success":
            return ConfirmResult(STILL_PENDING, attempt.order_id)  # not paid (yet)
        if (
            answer.reference != attempt.reference
            or answer.amount != attempt.amount_pesewas
            or answer.currency != attempt.currency
        ):
            attempt.status = PaymentAttempt.Status.MISMATCH
            attempt.save(update_fields=["status"])
            logger.error(
                "payment %s was reported paid with the wrong amount or currency: needs a person",
                attempt.reference,
            )
            return ConfirmResult(MISMATCH, attempt.order_id)
        try:
            outcome = settlement.settle_payment(attempt.order_id, attempt.amount_pesewas)
        except settlement.AmountMismatch:
            attempt.status = PaymentAttempt.Status.MISMATCH
            attempt.save(update_fields=["status"])
            logger.error(
                "payment %s does not match its order total: needs a person", attempt.reference
            )
            return ConfirmResult(MISMATCH, attempt.order_id)
        if outcome == settlement.ALREADY_PAID:
            attempt.status = PaymentAttempt.Status.DUPLICATE
            attempt.confirmed_at = timezone.now()
            attempt.save(update_fields=["status", "confirmed_at"])
            logger.error(
                "payment %s arrived for an order that was already paid: it needs a refund",
                attempt.reference,
            )
            return ConfirmResult(DUPLICATE, attempt.order_id)
        attempt.status = PaymentAttempt.Status.SUCCESS
        attempt.confirmed_at = timezone.now()
        attempt.save(update_fields=["status", "confirmed_at"])
        logger.info("payment %s applied: %s", attempt.reference, outcome)
        return ConfirmResult(outcome, attempt.order_id)


__all__ = [
    "ALREADY_CONFIRMED",
    "DUPLICATE",
    "FAILED",
    "MISMATCH",
    "NotPayable",
    "OrderNotFound",
    "PAID",
    "PAID_NOT_FULFILLABLE",
    "PAID_ORDER_CLOSED",
    "STILL_PENDING",
    "UNKNOWN_REFERENCE",
    "ConfirmResult",
    "StartResult",
    "TooManyAttempts",
    "confirm_reference",
    "start_payment",
]
