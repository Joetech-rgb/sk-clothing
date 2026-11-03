"""The order state machine. Pure Python: no database, no clock.

Three separate status fields (CLAUDE.md section 4): payment, fulfilment and refund. A change goes
through apply_event(), which either returns the new state or raises InvalidTransition. The caller
writes an OrderEvent row from the returned Transition. "Successful" and "unsuccessful" orders are
filters over these fields, never states orders move into.

Repeating an event that has already happened is a harmless no-op (changed=False), so a replayed
webhook or a double-clicked button cannot do damage.

The state tables are derived from the brief and ADR 0008, and are listed in ADR 0010 for the
client to confirm.
"""

from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import StrEnum


class Payment(StrEnum):
    PENDING = "pending"  # online payment not yet confirmed
    PAID = "paid"
    FAILED = "failed"  # an attempt failed; the customer may try again
    COD_PENDING = "cod_pending"  # pay on delivery, staff have not phoned yet
    COD_CONFIRMED = "cod_confirmed"  # staff confirmed by phone; cash is taken at delivery
    VOID = "void"  # the order was cancelled before any money was taken


class Fulfilment(StrEnum):
    AWAITING_QUOTE = "awaiting_quote"  # staff must set a delivery fee
    PENDING = "pending"  # waiting for payment or the COD phone call
    TO_PACK = "to_pack"
    PACKED = "packed"
    READY_FOR_PICKUP = "ready_for_pickup"
    OUT_FOR_DELIVERY = "out_for_delivery"
    DELIVERED = "delivered"
    COLLECTED = "collected"
    UNCOLLECTED = "uncollected"  # held 7 days, not collected
    CANCELLED = "cancelled"
    NOT_FULFILLABLE = "not_fulfillable"  # paid but no stock (ADR 0008)


class Refund(StrEnum):
    NONE = "none"
    REQUESTED = "requested"
    SUBMITTED = "submitted"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"
    MANUAL_RESOLUTION = "manual_resolution"


class Event(StrEnum):
    QUOTE_SET = "quote_set"
    PAYMENT_CONFIRMED = "payment_confirmed"
    PAYMENT_FAILED = "payment_failed"
    COD_CONFIRMED = "cod_confirmed"
    STOCK_UNAVAILABLE = "stock_unavailable"
    PACKED = "packed"
    READY_FOR_PICKUP = "ready_for_pickup"
    DISPATCHED = "dispatched"
    DELIVERED = "delivered"
    COLLECTED = "collected"
    FLAG_UNCOLLECTED = "flag_uncollected"
    CANCEL = "cancel"
    REFUND_SUBMITTED = "refund_submitted"
    REFUND_PROCESSING = "refund_processing"
    REFUND_PROCESSED = "refund_processed"
    REFUND_FAILED = "refund_failed"
    REFUND_RETRY = "refund_retry"
    REFUND_ESCALATED = "refund_escalated"
    REFUND_RESOLVED_MANUALLY = "refund_resolved_manually"


@dataclass(frozen=True)
class OrderState:
    payment: Payment
    fulfilment: Fulfilment
    refund: Refund = Refund.NONE
    pickup: bool = False  # collected in the shop, as opposed to delivered; never changes


@dataclass(frozen=True)
class Transition:
    event: Event
    before: OrderState
    after: OrderState

    @property
    def changed(self) -> bool:
        return self.before != self.after


class InvalidTransition(Exception):
    def __init__(self, state: OrderState, event: Event) -> None:
        super().__init__(f"{event.value} is not allowed from {state}")
        self.state = state
        self.event = event


# Fulfilment states that have been carried through to a final outcome.
FULFILMENT_TERMINAL = frozenset(
    {
        Fulfilment.DELIVERED,
        Fulfilment.COLLECTED,
        Fulfilment.CANCELLED,
        Fulfilment.NOT_FULFILLABLE,
    }
)
_DEAD = frozenset({Fulfilment.CANCELLED, Fulfilment.NOT_FULFILLABLE})
_COMMITTED = frozenset(
    {
        Fulfilment.TO_PACK,
        Fulfilment.PACKED,
        Fulfilment.READY_FOR_PICKUP,
        Fulfilment.OUT_FOR_DELIVERY,
        Fulfilment.DELIVERED,
        Fulfilment.COLLECTED,
    }
)


def initial_state(
    *, cod: bool = False, awaiting_quote: bool = False, pickup: bool = False
) -> OrderState:
    if cod and awaiting_quote:
        raise ValueError("pay on delivery is only offered when the delivery fee is known")
    if pickup and (cod or awaiting_quote):
        raise ValueError("pickup is free and is always paid online")
    return OrderState(
        payment=Payment.COD_PENDING if cod else Payment.PENDING,
        fulfilment=Fulfilment.AWAITING_QUOTE if awaiting_quote else Fulfilment.PENDING,
        pickup=pickup,
    )


# --- one small function per event: new state, the same state (a replay), or None (not allowed) ---

Handler = Callable[[OrderState], OrderState | None]


def _forward(
    allowed_from: set[Fulfilment],
    to: Fulfilment,
    *,
    payment_ok: set[Payment] | None = None,
    pickup: bool | None = None,  # True: pickup orders only. False: delivery orders only.
) -> Handler:
    def handle(s: OrderState) -> OrderState | None:
        if pickup is not None and s.pickup != pickup:
            return None
        if s.fulfilment == to:
            return s
        if s.fulfilment not in allowed_from:
            return None
        if payment_ok is not None and s.payment not in payment_ok:
            return None
        return replace(s, fulfilment=to)

    return handle


def _quote_set(s: OrderState) -> OrderState | None:
    return _forward({Fulfilment.AWAITING_QUOTE}, Fulfilment.PENDING)(s)


def _payment_confirmed(s: OrderState) -> OrderState | None:
    if s.payment == Payment.PAID:
        return s
    if s.payment not in {Payment.PENDING, Payment.FAILED, Payment.VOID}:
        return None
    if s.fulfilment == Fulfilment.AWAITING_QUOTE:
        return None  # the fee must be set before anyone can pay
    fulfilment = Fulfilment.TO_PACK if s.fulfilment == Fulfilment.PENDING else s.fulfilment
    refund = s.refund
    if fulfilment in _DEAD and refund == Refund.NONE:
        refund = Refund.REQUESTED  # money arrived for an order that is already dead
    return OrderState(Payment.PAID, fulfilment, refund, s.pickup)


def _payment_failed(s: OrderState) -> OrderState | None:
    if s.payment == Payment.FAILED:
        return s
    if s.payment != Payment.PENDING or s.fulfilment == Fulfilment.AWAITING_QUOTE:
        return None
    return replace(s, payment=Payment.FAILED)


def _cod_confirmed(s: OrderState) -> OrderState | None:
    if s.payment == Payment.COD_CONFIRMED:
        return s
    if s.payment != Payment.COD_PENDING or s.fulfilment != Fulfilment.PENDING:
        return None
    return replace(s, payment=Payment.COD_CONFIRMED, fulfilment=Fulfilment.TO_PACK)


def _void_if_unpaid(s: OrderState) -> Payment:
    unpaid = {Payment.PENDING, Payment.FAILED, Payment.COD_PENDING, Payment.COD_CONFIRMED}
    return Payment.VOID if s.payment in unpaid else s.payment


def _refund_if_paid(s: OrderState) -> Refund:
    if s.payment == Payment.PAID and s.refund == Refund.NONE:
        return Refund.REQUESTED
    return s.refund


def _stock_unavailable(s: OrderState) -> OrderState | None:
    if s.fulfilment == Fulfilment.NOT_FULFILLABLE:
        return s
    if s.fulfilment not in {Fulfilment.PENDING, Fulfilment.TO_PACK}:
        return None
    return OrderState(
        _void_if_unpaid(s), Fulfilment.NOT_FULFILLABLE, _refund_if_paid(s), s.pickup
    )


_CANCELLABLE = {
    Fulfilment.AWAITING_QUOTE,
    Fulfilment.PENDING,
    Fulfilment.TO_PACK,
    Fulfilment.PACKED,
    Fulfilment.READY_FOR_PICKUP,
    Fulfilment.UNCOLLECTED,
}


def _cancel(s: OrderState) -> OrderState | None:
    if s.fulfilment == Fulfilment.CANCELLED:
        return s
    if s.fulfilment not in _CANCELLABLE:
        return None
    return OrderState(_void_if_unpaid(s), Fulfilment.CANCELLED, _refund_if_paid(s), s.pickup)


def _delivered(s: OrderState) -> OrderState | None:
    if s.pickup:
        return None
    if s.fulfilment == Fulfilment.DELIVERED:
        return s
    if s.fulfilment != Fulfilment.OUT_FOR_DELIVERY:
        return None
    if s.payment not in {Payment.PAID, Payment.COD_CONFIRMED}:
        return None
    return replace(s, fulfilment=Fulfilment.DELIVERED, payment=Payment.PAID)  # COD cash collected


def _refund_step(allowed_from: set[Refund], to: Refund) -> Handler:
    def handle(s: OrderState) -> OrderState | None:
        if s.refund == to:
            return s
        if s.refund not in allowed_from:
            return None
        return replace(s, refund=to)

    return handle


_PAID = {Payment.PAID}
_HANDLERS: dict[Event, Handler] = {
    Event.QUOTE_SET: _quote_set,
    Event.PAYMENT_CONFIRMED: _payment_confirmed,
    Event.PAYMENT_FAILED: _payment_failed,
    Event.COD_CONFIRMED: _cod_confirmed,
    Event.STOCK_UNAVAILABLE: _stock_unavailable,
    Event.PACKED: _forward({Fulfilment.TO_PACK}, Fulfilment.PACKED),
    Event.READY_FOR_PICKUP: _forward(
        {Fulfilment.PACKED}, Fulfilment.READY_FOR_PICKUP, payment_ok=_PAID, pickup=True
    ),
    Event.DISPATCHED: _forward({Fulfilment.PACKED}, Fulfilment.OUT_FOR_DELIVERY, pickup=False),
    Event.DELIVERED: _delivered,
    Event.COLLECTED: _forward(
        {Fulfilment.READY_FOR_PICKUP}, Fulfilment.COLLECTED, payment_ok=_PAID, pickup=True
    ),
    Event.FLAG_UNCOLLECTED: _forward(
        {Fulfilment.READY_FOR_PICKUP}, Fulfilment.UNCOLLECTED, pickup=True
    ),
    Event.CANCEL: _cancel,
    Event.REFUND_SUBMITTED: _refund_step({Refund.REQUESTED}, Refund.SUBMITTED),
    Event.REFUND_PROCESSING: _refund_step({Refund.SUBMITTED}, Refund.PROCESSING),
    Event.REFUND_PROCESSED: _refund_step({Refund.SUBMITTED, Refund.PROCESSING}, Refund.PROCESSED),
    Event.REFUND_FAILED: _refund_step({Refund.SUBMITTED, Refund.PROCESSING}, Refund.FAILED),
    Event.REFUND_RETRY: _refund_step({Refund.FAILED}, Refund.REQUESTED),
    Event.REFUND_ESCALATED: _refund_step({Refund.FAILED}, Refund.MANUAL_RESOLUTION),
    Event.REFUND_RESOLVED_MANUALLY: _refund_step({Refund.MANUAL_RESOLUTION}, Refund.PROCESSED),
}


def apply_event(state: OrderState, event: Event) -> Transition:
    """Apply one event. Raises InvalidTransition if it is not allowed from this state."""
    after = _HANDLERS[event](state)
    if after is None:
        raise InvalidTransition(state, event)
    return Transition(event, state, after)


def check_invariants(state: OrderState) -> list[str]:
    """Rules that must hold for every order at every moment. Empty means consistent."""
    problems = []
    settled = {Payment.PAID, Payment.COD_CONFIRMED}
    if state.fulfilment in _COMMITTED and state.payment not in settled:
        problems.append("goods are being handled but nothing is paid or confirmed")
    if state.fulfilment in {Fulfilment.DELIVERED, Fulfilment.COLLECTED}:
        if state.payment != Payment.PAID:
            problems.append("an order was handed over without being paid")
    if state.payment == Payment.PAID and state.fulfilment in _DEAD and state.refund == Refund.NONE:
        problems.append("a paid order is dead with no refund started")
    if state.refund != Refund.NONE and state.payment != Payment.PAID:
        problems.append("a refund exists for an order that was never paid")
    if state.fulfilment == Fulfilment.AWAITING_QUOTE and state.payment in {
        Payment.PAID,
        Payment.FAILED,
    }:
        problems.append("a payment was attempted before the delivery fee was set")
    if state.pickup and state.fulfilment in {Fulfilment.OUT_FOR_DELIVERY, Fulfilment.DELIVERED}:
        problems.append("a pickup order was sent out for delivery")
    if not state.pickup and state.fulfilment in {
        Fulfilment.READY_FOR_PICKUP,
        Fulfilment.COLLECTED,
        Fulfilment.UNCOLLECTED,
    }:
        problems.append("a delivery order was put aside for collection")
    if state.pickup and state.payment in {Payment.COD_PENDING, Payment.COD_CONFIRMED}:
        problems.append("a pickup order cannot be pay on delivery")
    return problems
