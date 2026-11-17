import itertools

import pytest
from django.contrib.auth.models import Permission
from django.test import Client
from django.urls import reverse

from apps.delivery import code_services as codes
from apps.delivery.models import DeliveryCodeEvent
from apps.identity.models import User
from apps.orders import services
from apps.orders.models import Order
from apps.orders.services import LineInput, create_order, dispatch_order, mark_packed, transition
from apps.orders.states import Event, InvalidTransition
from apps.orders.tests.test_delivery_confirm import make_order, wrong_for
from apps.orders.views import order_json

_numbers = itertools.count(1)


def make_pickup_order():
    line = LineInput(
        variant_id=1,
        name="Test shirt",
        quantity=1,
        tier="retail",
        unit_price_pesewas=5000,
        list_price_pesewas=5000,
        tier_price_pesewas=5000,
        source="tier",
    )
    order, _ = create_order(
        idempotency_key=f"pickup-test-{next(_numbers):04d}",
        lines=[line],
        delivery_method="pickup",
        delivery_fee_pesewas=0,
        pickup=True,
    )
    transition(order.pk, Event.PAYMENT_CONFIRMED, actor="system:test")
    transition(order.pk, Event.PACKED, actor="system:test")
    return order


# --- the services --------------------------------------------------------------------------


def test_mark_packed_moves_a_paid_order_to_packed(db):
    order = make_order(upto="paid")
    mark_packed(order.pk, actor="user:5")
    order.refresh_from_db()
    assert order.fulfilment == "packed"
    assert order.events.last().actor == "user:5"


def test_mark_packed_refuses_an_order_that_is_not_paid_or_confirmed(db):
    line = LineInput(
        variant_id=1,
        name="Test shirt",
        quantity=1,
        tier="retail",
        unit_price_pesewas=5000,
        list_price_pesewas=5000,
        tier_price_pesewas=5000,
        source="tier",
    )
    order, _ = create_order(
        idempotency_key=f"unpaid-test-{next(_numbers):04d}",
        lines=[line],
        delivery_method="station",
        delivery_fee_pesewas=1000,
    )
    with pytest.raises(InvalidTransition):
        mark_packed(order.pk, actor="user:5")


def test_dispatch_sends_the_order_out_and_issues_the_code_together(db):
    order = make_order(upto="packed")
    code = dispatch_order(order.pk, actor="user:5")
    order.refresh_from_db()
    assert order.fulfilment == "out_for_delivery"
    assert codes.code_for_display(order.pk).code == code
    assert order_json(order)["delivery_code"] == code


def test_dispatching_twice_gives_the_same_code_and_one_history_line(db):
    order = make_order(upto="packed")
    first = dispatch_order(order.pk, actor="user:5")
    second = dispatch_order(order.pk, actor="user:5")
    assert first == second
    assert order.events.filter(event="dispatched").count() == 1
    assert DeliveryCodeEvent.objects.filter(order_id=order.pk, kind="issued").count() == 1


def test_an_order_that_is_not_packed_cannot_be_dispatched(db):
    order = make_order(upto="paid")
    with pytest.raises(InvalidTransition):
        dispatch_order(order.pk, actor="user:5")
    assert codes.code_for_display(order.pk).code is None  # no code was issued


def test_a_pickup_order_cannot_be_dispatched(db):
    order = make_pickup_order()
    with pytest.raises(InvalidTransition):
        dispatch_order(order.pk, actor="user:5")
    assert codes.code_for_display(order.pk).code is None


def test_a_delivered_order_cannot_be_dispatched_again(db):
    order = make_order(upto="packed")
    code = dispatch_order(order.pk, actor="user:5")
    services.confirm_delivery(order.reference, code, actor="user:6")
    with pytest.raises(InvalidTransition):
        dispatch_order(order.pk, actor="user:5")


# --- the whole journey (Stage 1, Week 5 exit check, without the SMS) ------------------------


def test_an_order_goes_from_paid_to_delivered_by_code(db):
    order = make_order(upto="paid")
    mark_packed(order.pk, actor="user:5")
    code = dispatch_order(order.pk, actor="user:5")
    order.refresh_from_db()
    assert order_json(order)["delivery_code"] == code

    assert services.confirm_delivery(order.reference, wrong_for(code), actor="user:6").status == (
        services.WRONG_CODE
    )
    result = services.confirm_delivery(order.reference, code, actor="user:6")
    assert result.status == services.DELIVERED_OK

    order.refresh_from_db()
    assert order.fulfilment == "delivered" and order.delivered_at is not None
    assert order_json(order)["delivery_code"] is None
    history = list(order.events.values_list("event", "actor"))
    assert history[-3:] == [("packed", "user:5"), ("dispatched", "user:5"), ("delivered", "user:6")]


# --- the admin actions ---------------------------------------------------------------------


def staff_with(*codenames):
    user = User.objects.create_user(
        email=f"staff{next(_numbers)}@example.test", password="not-a-real-password", is_staff=True
    )
    for name in ("view_order", *codenames):
        user.user_permissions.add(
            Permission.objects.get(content_type__app_label="orders", codename=name)
        )
    return user


def run_action(user, action, *orders):
    client = Client()
    client.force_login(user)
    return client.post(
        reverse("admin:orders_order_changelist"),
        {"action": action, "_selected_action": [order.pk for order in orders]},
    )


def test_staff_with_the_permission_can_pack_from_the_admin(db):
    order = make_order(upto="paid")
    response = run_action(staff_with("pack_order"), "mark_packed_action", order)
    assert response.status_code == 302
    order.refresh_from_db()
    assert order.fulfilment == "packed"


def test_staff_without_the_permission_cannot_pack_from_the_admin(db):
    order = make_order(upto="paid")
    run_action(staff_with(), "mark_packed_action", order)
    order.refresh_from_db()
    assert order.fulfilment == "to_pack"


def test_staff_with_the_permission_can_dispatch_and_a_code_is_issued(db):
    order = make_order(upto="packed")
    run_action(staff_with("dispatch_order"), "dispatch_action", order)
    order.refresh_from_db()
    assert order.fulfilment == "out_for_delivery"
    assert codes.code_for_display(order.pk).code is not None


def test_packing_permission_does_not_allow_dispatching(db):
    order = make_order(upto="packed")
    run_action(staff_with("pack_order"), "dispatch_action", order)
    order.refresh_from_db()
    assert order.fulfilment == "packed"


def test_staff_can_reissue_a_locked_code_from_the_admin(db):
    order = make_order(upto="packed")
    code = dispatch_order(order.pk, actor="user:5")
    for _ in range(5):
        services.confirm_delivery(order.reference, wrong_for(code), actor="user:6")
    assert codes.code_for_display(order.pk).locked is True
    run_action(staff_with("reissue_delivery_code"), "reissue_code_action", order)
    shown = codes.code_for_display(order.pk)
    assert shown.locked is False and shown.code is not None


def test_an_order_in_a_bad_state_is_skipped_not_broken(db):
    ready = make_order(upto="packed")
    unpaid_state = make_order(upto="paid")  # not packed yet, so dispatch does not apply
    run_action(staff_with("dispatch_order"), "dispatch_action", ready, unpaid_state)
    assert Order.objects.get(pk=ready.pk).fulfilment == "out_for_delivery"
    assert Order.objects.get(pk=unpaid_state.pk).fulfilment == "to_pack"
