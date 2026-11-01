from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.inventory import services as inventory
from apps.inventory.models import Reservation, StockLevel
from apps.orders import expiry
from apps.orders.models import Order
from apps.orders.services import transition
from apps.orders.states import Event, check_invariants
from apps.orders.tasks import cancel_stale_orders as cancel_task
from apps.orders.tests.test_checkout import ACCRA, body, place

pytestmark = pytest.mark.django_db

_n = {"i": 0}


def make(shop, items=None, **kwargs):
    """Place an order and return its row."""
    _n["i"] += 1
    items = items or [(shop.shirt, 1)]
    data = body(items, phone=kwargs.pop("phone", "0241234567"), **kwargs)
    response = place(APIClient(), data, key=f"expiry-key-{_n['i']:06d}")
    assert response.status_code == 201, response.content
    return Order.objects.get(reference=response.json()["reference"])


def age(order, hours):
    Order.objects.filter(pk=order.pk).update(created_at=timezone.now() - timedelta(hours=hours))
    order.refresh_from_db()


def fresh(order):
    return Order.objects.get(pk=order.pk)


def reserved(variant_id):
    return StockLevel.objects.get(variant_id=variant_id).reserved


def test_new_orders_are_left_alone(shop):
    make(shop)
    assert expiry.cancel_stale_orders() == 0
    assert Order.objects.get().fulfilment == "pending"


def test_an_unpaid_order_is_cancelled_after_a_day_and_its_stock_is_freed(shop):
    order = make(shop, [(shop.shirt, 2)])
    assert reserved(shop.shirt) == 2
    age(order, 25)
    assert expiry.cancel_stale_orders() == 1
    row = fresh(order)
    assert (row.payment, row.fulfilment, row.refund) == ("void", "cancelled", "none")
    assert check_invariants(row.state) == []
    assert reserved(shop.shirt) == 0 and StockLevel.objects.get(variant_id=shop.shirt).on_hand == 10
    assert list(row.events.values_list("event", "actor")) == [
        ("created", "guest"),
        ("cancel", "system:expiry"),
    ]
    assert not Reservation.objects.filter(status="active").exists()
    assert inventory.verify_ledger(shop.shirt) == []


def test_the_grace_period_is_a_full_day(shop):
    order = make(shop)
    age(order, 23.9)
    assert expiry.cancel_stale_orders() == 0
    age(order, 24.1)
    assert expiry.cancel_stale_orders() == 1


def test_an_order_whose_hold_ran_out_stays_payable_during_the_grace_period(shop):
    order = make(shop)
    from apps.inventory.models import ReservationStatus

    ids = list(order.reservations.values_list("reservation_id", flat=True))
    inventory._release(ids, ReservationStatus.EXPIRED)
    age(order, 5)  # the hold ran out hours ago, but the order is not cancelled
    assert expiry.cancel_stale_orders() == 0
    assert fresh(order).fulfilment == "pending"


def test_a_failed_payment_order_is_cancelled_too(shop):
    order = make(shop)
    transition(order.pk, Event.PAYMENT_FAILED, actor="test")
    age(order, 30)
    assert expiry.cancel_stale_orders() == 1
    assert fresh(order).payment == "void"


def test_a_paid_order_is_never_cancelled_however_old(shop):
    order = make(shop)
    transition(order.pk, Event.PAYMENT_CONFIRMED, actor="test")
    age(order, 24 * 100)
    assert expiry.cancel_stale_orders() == 0
    assert fresh(order).fulfilment == "to_pack"


def test_an_order_waiting_for_a_quote_gets_three_days(shop):
    order = make(shop, method="station", station_name="Tamale")
    assert order.fulfilment == "awaiting_quote"
    age(order, 48)
    assert expiry.cancel_stale_orders() == 0
    age(order, 73)
    assert expiry.cancel_stale_orders() == 1
    assert fresh(order).fulfilment == "cancelled" and reserved(shop.shirt) == 0


def test_pay_on_delivery_orders_get_three_days_unless_staff_confirm_them(shop):
    unconfirmed = make(shop, method="doorstep", cod=True, **ACCRA)
    confirmed = make(shop, method="doorstep", cod=True, phone="0249999999", **ACCRA)
    transition(confirmed.pk, Event.COD_CONFIRMED, actor="staff")
    for order in (unconfirmed, confirmed):
        age(order, 48)
    assert expiry.cancel_stale_orders() == 0
    for order in (unconfirmed, confirmed):
        age(order, 100)
    assert expiry.cancel_stale_orders() == 1
    assert fresh(unconfirmed).fulfilment == "cancelled"
    assert fresh(confirmed).fulfilment == "to_pack"


def test_running_it_again_does_nothing(shop):
    order = make(shop)
    age(order, 30)
    assert expiry.cancel_stale_orders() == 1
    assert expiry.cancel_stale_orders() == 0
    assert fresh(order).events.count() == 2


def test_many_stale_orders_are_handled_in_batches(shop):
    orders = [make(shop, phone=f"024123{n:04d}") for n in range(5)]
    for order in orders:
        age(order, 30)
    assert expiry.cancel_stale_orders(batch_size=2) == 5
    assert set(Order.objects.values_list("fulfilment", flat=True)) == {"cancelled"}
    assert reserved(shop.shirt) == 0 and inventory.verify_ledger(shop.shirt) == []


def test_only_the_stale_orders_are_touched(shop):
    stale = make(shop, phone="0241230001")
    young = make(shop, phone="0241230002")
    paid = make(shop, phone="0241230003")
    transition(paid.pk, Event.PAYMENT_CONFIRMED, actor="test")
    age(stale, 30)
    age(paid, 30)
    assert expiry.cancel_stale_orders() == 1
    assert fresh(stale).fulfilment == "cancelled"
    assert fresh(young).fulfilment == "pending" and fresh(paid).fulfilment == "to_pack"
    assert reserved(shop.shirt) == 2  # the young order's hold and the paid order's hold


def test_the_limits_can_be_changed_in_settings(shop, settings):
    settings.ORDER_EXPIRY_HOURS = {"unpaid_online": 1}
    order = make(shop)
    age(order, 2)
    assert expiry.cancel_stale_orders() == 1


def test_the_freed_stock_can_be_bought_by_someone_else(shop):
    order = make(shop, [(shop.scarce, 1)])
    other = place(APIClient(), body([(shop.scarce, 1)], phone="0249999999"), key="expiry-other-001")
    assert other.status_code == 409
    age(order, 30)
    expiry.cancel_stale_orders()
    again = place(APIClient(), body([(shop.scarce, 1)], phone="0249999999"), key="expiry-other-002")
    assert again.status_code == 201


def test_a_cancelled_order_whose_hold_was_already_released_is_fine(shop):
    order = make(shop)
    from apps.inventory.models import ReservationStatus

    inventory._release(
        list(order.reservations.values_list("reservation_id", flat=True)), ReservationStatus.EXPIRED
    )
    age(order, 30)
    assert expiry.cancel_stale_orders() == 1
    assert reserved(shop.shirt) == 0 and inventory.verify_ledger(shop.shirt) == []


def test_the_scheduled_task_does_the_same_and_reports_how_many(shop):
    for n in range(3):
        age(make(shop, phone=f"024123{n:04d}"), 30)
    assert cancel_task() == 3
    assert cancel_task() == 0
