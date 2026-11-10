"""Order services. Other apps call these, never the order models directly."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.delivery import code_services as delivery_codes

from .models import Order, OrderEvent, OrderLine, SubOrder
from .states import (
    Event,
    Fulfilment,
    InvalidTransition,
    OrderState,
    Transition,
    apply_event,
    check_invariants,
    initial_state,
)


class InconsistentState(RuntimeError):
    """A transition would leave the order breaking an invariant. This is a bug, not user error."""


@dataclass(frozen=True)
class LineInput:
    """One line to freeze onto the order, already priced by the server (never by the client)."""

    variant_id: int
    name: str
    quantity: int
    tier: str
    unit_price_pesewas: int
    list_price_pesewas: int
    tier_price_pesewas: int
    source: str
    discounts: tuple[dict, ...] = ()

    @property
    def line_total_pesewas(self) -> int:
        return self.unit_price_pesewas * self.quantity


def _snapshot(state: OrderState) -> dict:
    return {
        "payment": state.payment.value,
        "fulfilment": state.fulfilment.value,
        "refund": state.refund.value,
        "pickup": state.pickup,
    }


def create_order(
    *,
    idempotency_key: str,
    lines: Sequence[LineInput],
    delivery_method: str,
    delivery_fee_pesewas: int | None,
    cod: bool = False,
    awaiting_quote: bool = False,
    pickup: bool = False,
    user_id: int | None = None,
    contact_phone: str = "",
    contact_name: str = "",
    delivery_details: dict | None = None,
    request_hash: str = "",
    actor: str = "system",
) -> tuple[Order, bool]:
    """Create an order with its lines frozen. Returns (order, created).

    Repeating the same idempotency key returns the existing order and creates nothing.
    """
    if not idempotency_key:
        raise ValueError("an idempotency key is required")
    if not lines:
        raise ValueError("an order needs at least one line")
    if awaiting_quote and delivery_fee_pesewas is not None:
        raise ValueError("an order awaiting a quote has no delivery fee yet")
    if not awaiting_quote and delivery_fee_pesewas is None:
        raise ValueError("a delivery fee is required unless the order awaits a quote")
    if pickup and delivery_fee_pesewas != 0:
        raise ValueError("pickup is free")
    state = initial_state(cod=cod, awaiting_quote=awaiting_quote, pickup=pickup)

    existing = Order.objects.filter(idempotency_key=idempotency_key).first()
    if existing is not None:
        return existing, False
    try:
        with transaction.atomic():
            order = Order.objects.create(
                idempotency_key=idempotency_key,
                user_id=user_id,
                contact_phone=contact_phone,
                contact_name=contact_name,
                delivery_details=delivery_details or {},
                request_hash=request_hash,
                payment=state.payment.value,
                fulfilment=state.fulfilment.value,
                refund=state.refund.value,
                pickup=pickup,
                delivery_method=delivery_method,
                delivery_fee_pesewas=delivery_fee_pesewas,
                subtotal_pesewas=sum(line.line_total_pesewas for line in lines),
            )
            SubOrder.objects.create(order=order)
            OrderLine.objects.bulk_create(
                OrderLine(
                    order=order,
                    variant_id=line.variant_id,
                    name=line.name,
                    quantity=line.quantity,
                    tier=line.tier,
                    unit_price_pesewas=line.unit_price_pesewas,
                    line_total_pesewas=line.line_total_pesewas,
                    list_price_pesewas=line.list_price_pesewas,
                    tier_price_pesewas=line.tier_price_pesewas,
                    source=line.source,
                    discounts=list(line.discounts),
                )
                for line in lines
            )
            OrderEvent.objects.create(
                order=order, event="created", before=None, after=_snapshot(state), actor=actor
            )
    except IntegrityError:
        existing = Order.objects.filter(idempotency_key=idempotency_key).first()
        if existing is not None:  # a concurrent request with the same key won
            return existing, False
        raise
    return order, True


def transition(order_id: int, event: Event | str, *, actor: str) -> Transition:
    """Apply one event to an order. The only way an order's status fields change.

    Locks the order row, so concurrent events apply one at a time. A repeated event is a no-op
    and writes no history. An event that is not allowed raises InvalidTransition and changes
    nothing.
    """
    event = Event(event)
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order_id)
        result = apply_event(order.state, event)
        if not result.changed:
            return result
        problems = check_invariants(result.after)
        if problems:
            raise InconsistentState("; ".join(problems))
        order.payment = result.after.payment.value
        order.fulfilment = result.after.fulfilment.value
        order.refund = result.after.refund.value
        update_fields = ["payment", "fulfilment", "refund", "updated_at"]
        if event == Event.DELIVERED and order.delivered_at is None:
            order.delivered_at = timezone.now()  # starts the return clock and commission hold
            update_fields.append("delivered_at")
        order.save(update_fields=update_fields)
        OrderEvent.objects.create(
            order=order,
            event=event.value,
            before=_snapshot(result.before),
            after=_snapshot(result.after),
            actor=actor,
        )
    return result


DELIVERED_OK = "delivered"
ALREADY_DELIVERED = "already_delivered"
ORDER_NOT_FOUND = "order_not_found"
NOT_OUT_FOR_DELIVERY = "not_out_for_delivery"
WRONG_CODE = "wrong_code"
MALFORMED_CODE = "malformed_code"
CODE_LOCKED = "code_locked"
NO_DELIVERY_CODE = "no_delivery_code"

_CODE_OUTCOMES = {
    delivery_codes.WRONG: WRONG_CODE,
    delivery_codes.MALFORMED: MALFORMED_CODE,
    delivery_codes.LOCKED: CODE_LOCKED,
    delivery_codes.NO_CODE: NO_DELIVERY_CODE,
}


@dataclass(frozen=True)
class ConfirmResult:
    status: str
    delivered_at: datetime | None = None


def confirm_delivery(reference: str, submitted: str, *, actor: str) -> ConfirmResult:
    """A rider or staff member enters the delivery code. The caller has already checked that they
    may. A correct code marks the order delivered and records who confirmed it and when.

    Everything happens under a lock on the order, so two people entering the code at once deliver
    it once. A wrong or locked code is returned, not raised: raising would roll back the count of
    wrong attempts, and the count is what stops guessing. Repeating a correct code is a no-op.
    """
    try:
        with transaction.atomic():
            order = Order.objects.select_for_update().filter(reference=reference).first()
            if order is None:
                return ConfirmResult(ORDER_NOT_FOUND)
            if order.fulfilment == Fulfilment.DELIVERED.value:
                return ConfirmResult(ALREADY_DELIVERED, order.delivered_at)
            if order.fulfilment != Fulfilment.OUT_FOR_DELIVERY.value:
                return ConfirmResult(NOT_OUT_FOR_DELIVERY)
            outcome = delivery_codes.check_delivery_code(order.pk, submitted, actor=actor)
            if outcome != delivery_codes.OK:
                return ConfirmResult(_CODE_OUTCOMES[outcome])
            transition(order.pk, Event.DELIVERED, actor=actor)
            delivery_codes.mark_code_used(order.pk, actor=actor)
            order.refresh_from_db(fields=["delivered_at"])
            return ConfirmResult(DELIVERED_OK, order.delivered_at)
    except InvalidTransition:  # raised inside the block, so nothing above was kept
        return ConfirmResult(NOT_OUT_FOR_DELIVERY)


def mark_packed(order_id: int, *, actor: str) -> Transition:
    """Staff finished packing an order that is paid (or confirmed for pay on delivery)."""
    return transition(order_id, Event.PACKED, actor=actor)


def dispatch_order(order_id: int, *, actor: str) -> str:
    """Send a packed delivery order out and issue its delivery code, in one transaction.

    Returns the code so the caller can send it. Never log it. Repeating this is safe: the order
    does not move twice and the same code comes back. Raises InvalidTransition for a pickup
    order, an order that is not packed, or one that is already delivered.
    """
    with transaction.atomic():
        transition(order_id, Event.DISPATCHED, actor=actor)
        return delivery_codes.issue_delivery_code(order_id, actor=actor)
