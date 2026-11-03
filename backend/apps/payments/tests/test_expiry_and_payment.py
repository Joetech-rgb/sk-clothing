import pytest

from apps.orders import expiry
from apps.orders.models import Order
from apps.payments.tests.helpers import (
    attempts,
    fake,
    level,
    order_row,
    place_order,
    start,
    start_ok,
    verify_page,
)

pytestmark = pytest.mark.django_db


def make_stale(order_reference):
    from datetime import timedelta

    from django.utils import timezone

    Order.objects.filter(reference=order_reference).update(
        created_at=timezone.now() - timedelta(hours=30)
    )


def test_an_order_cancelled_for_not_paying_cannot_be_paid_for_any_more(shop):
    order = place_order([(shop.shirt, 1)])
    make_stale(order["reference"])
    assert expiry.cancel_stale_orders() == 1
    response = start(order["reference"])
    assert response.status_code == 409
    assert response.json()["error"]["details"]["why"] == "order_closed"


def test_money_that_arrives_after_the_order_was_cancelled_is_refunded_not_kept(shop):
    order = place_order([(shop.shirt, 2)])
    reference = start_ok(order["reference"])  # the customer is already on Paystack's page
    make_stale(order["reference"])
    expiry.cancel_stale_orders()
    assert verify_page(reference).json()["outcome"] == "paid_order_closed"
    row = order_row(order["reference"])
    assert (row.payment, row.fulfilment, row.refund) == ("paid", "cancelled", "requested")
    assert (level(shop.shirt).on_hand, level(shop.shirt).reserved) == (10, 0)
    assert attempts(order["reference"]).get().status == "success"
    assert fake().verify_calls == [reference]


def test_paying_during_the_grace_period_after_the_hold_ran_out_still_works(shop):
    from apps.payments.tests.helpers import expire_holds

    order = place_order([(shop.shirt, 2)])
    reference = start_ok(order["reference"])
    expire_holds(order["reference"])
    assert expiry.cancel_stale_orders() == 0  # not old enough to cancel
    assert verify_page(reference).json()["outcome"] == "paid"
    assert order_row(order["reference"]).fulfilment == "to_pack"
