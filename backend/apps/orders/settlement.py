"""What payment does to an order and its stock. Called by the payments app, never the other way.

Rules (ADR 0008):
- Hold still active: the held stock becomes a sale.
- Hold expired or released: try to reserve the stock again and sell it, in the same transaction.
- No stock any more: never oversell. The order is marked paid but not fulfillable, and a refund
  is requested.
- An order that was cancelled before the money arrived stays cancelled, and a refund is requested.
Paying twice never sells twice: the order's payment status decides, under a row lock.
"""

import logging
from dataclasses import dataclass

from django.db import transaction

from apps.inventory import services as inventory
from apps.inventory.errors import InsufficientStock, ReservationNotActive

from .models import Order, OrderReservation
from .services import transition
from .states import Event, Fulfilment, InvalidTransition, Payment

logger = logging.getLogger(__name__)

PAID = "paid"
ALREADY_PAID = "already_paid"
PAID_NOT_FULFILLABLE = "paid_not_fulfillable"
PAID_ORDER_CLOSED = "paid_order_closed"


class OrderNotFound(Exception):
    pass


class NotPayable(Exception):
    def __init__(self, why: str) -> None:
        super().__init__(why)
        self.why = why


class AmountMismatch(Exception):
    pass


@dataclass(frozen=True)
class PayableOrder:
    order_id: int
    reference: str
    total_pesewas: int


def payable_order(reference: str) -> PayableOrder:
    """The order a customer may pay for now, or raise OrderNotFound or NotPayable."""
    order = Order.objects.filter(reference=reference).first()
    if order is None:
        raise OrderNotFound
    if order.delivery_fee_pesewas is None:
        raise NotPayable("awaiting_quote")
    if order.payment in (Payment.COD_PENDING.value, Payment.COD_CONFIRMED.value):
        raise NotPayable("pay_on_delivery")
    if order.payment == Payment.PAID.value:
        raise NotPayable("already_paid")
    if order.payment not in (Payment.PENDING.value, Payment.FAILED.value):
        raise NotPayable("order_closed")
    if order.fulfilment != Fulfilment.PENDING.value:
        raise NotPayable("order_closed")
    return PayableOrder(order.pk, order.reference, order.total_pesewas)


def order_summary(order_id: int) -> dict | None:
    """The statuses a customer may see for their order."""
    order = Order.objects.filter(pk=order_id).first()
    if order is None:
        return None
    return {
        "order_reference": order.reference,
        "payment_status": order.payment,
        "fulfilment_status": order.fulfilment,
        "refund_status": order.refund,
    }


def mark_payment_failed(order_id: int) -> bool:
    """Record a failed attempt. The customer may try again. False if it cannot apply (for
    example the order was paid by another attempt in the meantime)."""
    try:
        transition(order_id, Event.PAYMENT_FAILED, actor="system:payment")
    except InvalidTransition:
        return False
    return True


def _sell_again(order: Order) -> str:
    """The hold ran out. Release any part of it that is still held, then take the stock again
    and sell it. Returns PAID or PAID_NOT_FULFILLABLE. All inside the caller's transaction."""
    holds = list(order.reservations.all())
    inventory.release([hold.reservation_id for hold in holds])
    wanted = {}
    for hold in holds:
        wanted[hold.variant_id] = wanted.get(hold.variant_id, 0) + hold.quantity
    try:
        fresh = inventory.reserve_many(
            [
                inventory.StockRequest(variant_id, quantity)
                for variant_id, quantity in wanted.items()
            ],
            idempotency_key=f"late:{order.pk}",
        )
        inventory.confirm_sale([reservation.pk for reservation in fresh])
    except InsufficientStock:
        transition(order.pk, Event.STOCK_UNAVAILABLE, actor="system:payment")
        return PAID_NOT_FULFILLABLE
    OrderReservation.objects.bulk_create(
        OrderReservation(
            order=order,
            reservation_id=reservation.pk,
            variant_id=reservation.variant_id,
            quantity=reservation.quantity,
            expires_at=reservation.expires_at,
        )
        for reservation in fresh
    )
    return PAID


def settle_payment(order_id: int, paid_pesewas: int) -> str:
    """Apply a verified payment. Safe to repeat and safe to run concurrently.

    Returns PAID, PAID_NOT_FULFILLABLE, PAID_ORDER_CLOSED, or ALREADY_PAID (the order was paid
    before: nothing changes, so this money is a second payment). Raises AmountMismatch if the
    amount is not exactly the order total.
    """
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order_id)
        if paid_pesewas != order.total_pesewas:
            raise AmountMismatch
        result = transition(order.pk, Event.PAYMENT_CONFIRMED, actor="system:payment")
        if not result.changed:
            return ALREADY_PAID
        if result.after.fulfilment in (Fulfilment.CANCELLED, Fulfilment.NOT_FULFILLABLE):
            return PAID_ORDER_CLOSED  # the state machine has already requested the refund
        holds = [hold.reservation_id for hold in order.reservations.all()]
        try:
            inventory.confirm_sale(holds)
        except ReservationNotActive:
            return _sell_again(order)
        return PAID
