import pytest
from django.db import IntegrityError, transaction

from apps.orders.models import ImmutableError, Order, OrderEvent, OrderLine
from apps.orders.services import InconsistentState, LineInput, create_order, transition
from apps.orders.states import (
    Event,
    Fulfilment,
    InvalidTransition,
    Payment,
    Refund,
    check_invariants,
)

pytestmark = pytest.mark.django_db


def line(**overrides):
    values = dict(
        variant_id=1,
        name="Red shirt, M",
        quantity=3,
        tier="retail",
        unit_price_pesewas=5000,
        list_price_pesewas=5000,
        tier_price_pesewas=5000,
        source="tier",
    )
    values.update(overrides)
    return LineInput(**values)


def make(key="k1", **overrides):
    args = dict(
        idempotency_key=key,
        lines=[line()],
        delivery_method="station",
        delivery_fee_pesewas=1500,
    )
    args.update(overrides)
    return create_order(**args)


def events_of(order):
    return list(order.events.values_list("event", flat=True))


# --- creation ---------------------------------------------------------------------------------


def test_create_freezes_lines_and_totals():
    order, created = make(
        lines=[line(quantity=3), line(variant_id=2, quantity=1, unit_price_pesewas=700)]
    )
    assert created
    assert order.subtotal_pesewas == 3 * 5000 + 700
    assert order.total_pesewas == order.subtotal_pesewas + 1500
    assert order.lines.count() == 2
    assert order.sub_order.vendor_id is None
    assert events_of(order) == ["created"]
    assert order.reference.startswith("SK") and len(order.reference) == 12


def test_create_stores_discount_detail_on_line():
    detail = {"name": "Eid sale", "kind": "percentage", "amount_pesewas": 1000}
    order, _ = make(lines=[line(source="discount", discounts=(detail,))])
    assert order.lines.get().discounts == [detail]


@pytest.mark.parametrize(
    ("kwargs", "payment", "fulfilment"),
    [
        ({}, Payment.PENDING, Fulfilment.PENDING),
        ({"cod": True}, Payment.COD_PENDING, Fulfilment.PENDING),
        (
            {"awaiting_quote": True, "delivery_fee_pesewas": None},
            Payment.PENDING,
            Fulfilment.AWAITING_QUOTE,
        ),
        (
            {"pickup": True, "delivery_method": "pickup", "delivery_fee_pesewas": 0},
            Payment.PENDING,
            Fulfilment.PENDING,
        ),
    ],
)
def test_initial_state_matches_state_machine(kwargs, payment, fulfilment):
    order, _ = make(**kwargs)
    assert order.state.payment == payment
    assert order.state.fulfilment == fulfilment
    assert order.state.refund == Refund.NONE
    assert check_invariants(order.state) == []


def test_awaiting_quote_order_has_no_total_yet():
    order, _ = make(awaiting_quote=True, delivery_fee_pesewas=None)
    assert order.total_pesewas is None


@pytest.mark.parametrize(
    "kwargs",
    [
        {"lines": []},
        {"idempotency_key": ""},
        {"awaiting_quote": True},  # fee given but should be unknown
        {"delivery_fee_pesewas": None},  # fee missing and not awaiting a quote
        {"pickup": True, "delivery_fee_pesewas": 500},
        {"cod": True, "awaiting_quote": True, "delivery_fee_pesewas": None},
        {"pickup": True, "cod": True, "delivery_fee_pesewas": 0},
    ],
)
def test_bad_creation_input_is_refused_and_writes_nothing(kwargs):
    with pytest.raises(ValueError):
        make(**kwargs)
    assert Order.objects.count() == 0


def test_same_idempotency_key_returns_same_order():
    first, created_first = make("same")
    second, created_second = make("same", lines=[line(quantity=99)])
    assert (created_first, created_second) == (True, False)
    assert first.pk == second.pk
    assert Order.objects.count() == 1
    assert OrderLine.objects.count() == 1
    assert second.lines.get().quantity == 3  # the first request's data, not the repeat's
    assert events_of(first) == ["created"]


def test_database_rejects_duplicate_idempotency_key():
    make("dup")
    with pytest.raises(IntegrityError), transaction.atomic():
        Order.objects.create(
            idempotency_key="dup",
            payment="pending",
            fulfilment="pending",
            pickup=False,
            delivery_method="station",
            subtotal_pesewas=0,
            delivery_fee_pesewas=0,
        )


def test_database_rejects_line_total_that_is_not_price_times_quantity():
    order, _ = make()
    with pytest.raises(IntegrityError), transaction.atomic():
        OrderLine.objects.create(
            order=order,
            variant_id=1,
            name="x",
            quantity=2,
            tier="retail",
            unit_price_pesewas=100,
            line_total_pesewas=999,
            list_price_pesewas=100,
            tier_price_pesewas=100,
            source="tier",
        )


def test_database_rejects_zero_quantity_and_negative_subtotal():
    order, _ = make()
    with pytest.raises(IntegrityError), transaction.atomic():
        OrderLine.objects.create(
            order=order,
            variant_id=1,
            name="x",
            quantity=0,
            tier="retail",
            unit_price_pesewas=100,
            line_total_pesewas=0,
            list_price_pesewas=100,
            tier_price_pesewas=100,
            source="tier",
        )
    with pytest.raises(IntegrityError), transaction.atomic():
        Order.objects.filter(pk=order.pk).update(subtotal_pesewas=-1)


# --- transitions ------------------------------------------------------------------------------


def test_delivery_order_walks_to_delivered_and_every_step_is_recorded():
    order, _ = make()
    for event in (Event.PAYMENT_CONFIRMED, Event.PACKED, Event.DISPATCHED, Event.DELIVERED):
        transition(order.pk, event, actor="test")
        order.refresh_from_db()
        assert check_invariants(order.state) == []
    assert (order.payment, order.fulfilment) == ("paid", "delivered")
    assert events_of(order) == ["created", "payment_confirmed", "packed", "dispatched", "delivered"]
    last = order.events.last()
    assert last.before["fulfilment"] == "out_for_delivery"
    assert last.after["fulfilment"] == "delivered"
    assert last.actor == "test"


def test_pickup_order_walks_to_collected():
    order, _ = make(pickup=True, delivery_method="pickup", delivery_fee_pesewas=0)
    for event in (Event.PAYMENT_CONFIRMED, Event.PACKED, Event.READY_FOR_PICKUP, Event.COLLECTED):
        transition(order.pk, event, actor="test")
    order.refresh_from_db()
    assert order.fulfilment == "collected"
    assert check_invariants(order.state) == []


def test_cod_delivery_marks_cash_as_paid():
    order, _ = make(cod=True)
    for event in (Event.COD_CONFIRMED, Event.PACKED, Event.DISPATCHED, Event.DELIVERED):
        transition(order.pk, event, actor="test")
    order.refresh_from_db()
    assert (order.payment, order.fulfilment) == ("paid", "delivered")


def test_unlisted_station_quote_then_payment():
    order, _ = make(awaiting_quote=True, delivery_fee_pesewas=None)
    with pytest.raises(InvalidTransition):
        transition(order.pk, Event.PAYMENT_CONFIRMED, actor="test")  # fee not set yet
    transition(order.pk, Event.QUOTE_SET, actor="test")
    transition(order.pk, Event.PAYMENT_CONFIRMED, actor="test")
    order.refresh_from_db()
    assert (order.payment, order.fulfilment) == ("paid", "to_pack")


def test_replayed_event_changes_nothing_and_writes_no_history():
    order, _ = make()
    for _ in range(3):  # a webhook delivered three times
        transition(order.pk, Event.PAYMENT_CONFIRMED, actor="system:paystack_webhook")
    assert events_of(order) == ["created", "payment_confirmed"]
    order.refresh_from_db()
    assert order.payment == "paid"


def test_illegal_event_raises_and_changes_nothing():
    order, _ = make()
    before = Order.objects.values().get(pk=order.pk)
    with pytest.raises(InvalidTransition):
        transition(order.pk, Event.DELIVERED, actor="test")  # nothing is paid or packed
    assert Order.objects.values().get(pk=order.pk) == before
    assert events_of(order) == ["created"]


def test_unknown_event_name_is_refused():
    order, _ = make()
    with pytest.raises(ValueError):
        transition(order.pk, "teleported", actor="test")


def test_cancelling_a_paid_order_requests_a_refund():
    order, _ = make()
    transition(order.pk, Event.PAYMENT_CONFIRMED, actor="test")
    transition(order.pk, Event.CANCEL, actor="user:1")
    order.refresh_from_db()
    assert (order.payment, order.fulfilment, order.refund) == ("paid", "cancelled", "requested")
    assert check_invariants(order.state) == []


def test_cancelling_an_unpaid_order_voids_it_without_a_refund():
    order, _ = make()
    transition(order.pk, Event.CANCEL, actor="user:1")
    order.refresh_from_db()
    assert (order.payment, order.refund) == ("void", "none")


def test_late_payment_on_a_dead_order_requests_a_refund():
    order, _ = make()
    transition(order.pk, Event.STOCK_UNAVAILABLE, actor="system")
    transition(order.pk, Event.PAYMENT_CONFIRMED, actor="system:paystack_webhook")
    order.refresh_from_db()
    assert (order.payment, order.fulfilment, order.refund) == (
        "paid",
        "not_fulfillable",
        "requested",
    )


def test_a_transition_that_would_break_an_invariant_is_rolled_back(monkeypatch):
    order, _ = make()
    monkeypatch.setattr("apps.orders.services.check_invariants", lambda state: ["forced problem"])
    with pytest.raises(InconsistentState):
        transition(order.pk, Event.PAYMENT_CONFIRMED, actor="test")
    order.refresh_from_db()
    assert order.payment == "pending"
    assert events_of(order) == ["created"]


def test_pickup_flag_never_changes_through_transitions():
    order, _ = make(pickup=True, delivery_method="pickup", delivery_fee_pesewas=0)
    transition(order.pk, Event.PAYMENT_CONFIRMED, actor="test")
    order.refresh_from_db()
    assert order.pickup is True


# --- immutability -----------------------------------------------------------------------------


def test_order_lines_cannot_be_changed_or_deleted():
    order, _ = make()
    the_line = order.lines.get()
    the_line.unit_price_pesewas = 1
    with pytest.raises(ImmutableError):
        the_line.save()
    with pytest.raises(ImmutableError):
        the_line.delete()
    with pytest.raises(ImmutableError):
        OrderLine.objects.filter(pk=the_line.pk).update(unit_price_pesewas=1)
    with pytest.raises(ImmutableError):
        OrderLine.objects.filter(pk=the_line.pk).delete()
    assert order.lines.get().unit_price_pesewas == 5000


def test_order_history_cannot_be_rewritten():
    order, _ = make()
    event = order.events.get()
    event.event = "tampered"
    with pytest.raises(ImmutableError):
        event.save()
    with pytest.raises(ImmutableError):
        OrderEvent.objects.all().delete()
    with pytest.raises(ImmutableError):
        OrderEvent.objects.update(actor="someone else")


def test_orders_cannot_be_deleted():
    order, _ = make()
    with pytest.raises(ImmutableError):
        order.delete()
    assert Order.objects.count() == 1


# --- admin is read-only -----------------------------------------------------------------------


def test_admin_is_read_only():
    from django.contrib import admin
    from django.test import RequestFactory

    model_admin = admin.site._registry[Order]
    request = RequestFactory().get("/")
    assert not model_admin.has_add_permission(request)
    assert not model_admin.has_change_permission(request)
    assert not model_admin.has_delete_permission(request)
