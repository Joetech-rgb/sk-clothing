"""The expiry job racing itself and racing a payment, on a real PostgreSQL database."""

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from django.db import connections
from django.utils import timezone

from apps.inventory import services as inventory
from apps.inventory.models import StockLevel, StockMovement
from apps.orders import expiry, settlement
from apps.orders.models import Order
from apps.orders.tests.test_expiry import make

pytestmark = pytest.mark.django_db(transaction=True)


def in_parallel(count, work):
    barrier = threading.Barrier(count)

    def run(i):
        try:
            barrier.wait(timeout=30)
            return work(i)
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=count) as pool:
        return list(pool.map(run, range(count)))


def age_all():
    Order.objects.update(created_at=timezone.now() - timedelta(hours=30))


def test_several_runs_at_once_cancel_each_order_exactly_once(shop):
    for n in range(6):
        make(shop, phone=f"024123{n:04d}")
    age_all()
    totals = in_parallel(8, lambda i: expiry.cancel_stale_orders(batch_size=2))
    assert sum(totals) == 6
    for order in Order.objects.all():
        assert list(order.events.values_list("event", flat=True)).count("cancel") == 1
    assert StockLevel.objects.get(variant_id=shop.shirt).reserved == 0
    assert inventory.verify_ledger(shop.shirt) == []


@pytest.mark.parametrize("head_start", ["payment", "cancel"] + ["neither"] * 6)
def test_a_payment_and_the_expiry_job_never_leave_an_order_half_done(shop, head_start):
    order = make(shop, [(shop.shirt, 2)])
    age_all()

    def work(i):
        if (i == 0 and head_start == "cancel") or (i == 1 and head_start == "payment"):
            time.sleep(0.4)
        if i == 0:
            return ("pay", settlement.settle_payment(order.pk, order.total_pesewas))
        return ("cancel", expiry.cancel_if_stale(order.pk, timezone.now()))

    results = dict(in_parallel(2, work))
    row = Order.objects.get(pk=order.pk)
    level = StockLevel.objects.get(variant_id=shop.shirt)
    sold = StockMovement.objects.filter(variant_id=shop.shirt, kind="sale").count()
    assert row.payment == "paid"  # a cancelled order that is then paid is still "paid"
    if results["cancel"]:  # cancelled first: the late payment is refunded, nothing is sold
        assert row.fulfilment == "cancelled"
        assert results["pay"] == settlement.PAID_ORDER_CLOSED
        assert (row.payment, row.refund) == ("paid", "requested")
        assert sold == 0 and (level.on_hand, level.reserved) == (10, 0)
    else:  # paid first: the cancel job leaves it alone
        assert (row.payment, row.fulfilment, row.refund) == ("paid", "to_pack", "none")
        assert sold == 1 and (level.on_hand, level.reserved) == (8, 0)
    if head_start == "payment":
        assert results["cancel"] is False
    if head_start == "cancel":
        assert results["cancel"] is True
    assert inventory.verify_ledger(shop.shirt) == []


def test_the_outcomes_are_only_ever_one_of_two(shop):
    order = make(shop)
    age_all()
    results = in_parallel(
        6,
        lambda i: (
            ("pay", settlement.settle_payment(order.pk, order.total_pesewas))
            if i % 2
            else ("cancel", expiry.cancel_if_stale(order.pk, timezone.now()))
        ),
    )
    row = Order.objects.get(pk=order.pk)
    cancels = [outcome for kind, outcome in results if kind == "cancel" and outcome]
    assert len(cancels) <= 1  # the order is cancelled at most once
    assert (row.fulfilment, row.refund) in (("to_pack", "none"), ("cancelled", "requested"))
