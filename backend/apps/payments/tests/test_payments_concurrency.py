"""Simultaneous payments on a real PostgreSQL database: a payment is applied once, money for an
already-paid order is flagged and not sold again, and a late payer racing a new buyer for the last
unit never oversells."""

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from django.db import connection, connections
from rest_framework.test import APIClient

from apps.inventory import services as inventory
from apps.inventory.models import StockMovement
from apps.payments.tests.helpers import (
    attempts,
    expire_holds,
    level,
    order_row,
    place_order,
    start_ok,
    verify_page,
    webhook,
)

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


def sales(variant_id):
    return StockMovement.objects.filter(variant_id=variant_id, kind="sale").count()


def test_the_database_runs_postgresql():
    assert connection.vendor == "postgresql"


def test_one_payment_reported_many_times_at_once_is_applied_once(shop):
    order = place_order([(shop.shirt, 2)])
    reference = start_ok(order["reference"])

    def work(i):
        return webhook(reference) if i % 2 else verify_page(reference)

    responses = in_parallel(16, work)
    assert {r.status_code for r in responses} == {200}
    row = order_row(order["reference"])
    assert (row.payment, row.fulfilment) == ("paid", "to_pack")
    assert (level(shop.shirt).on_hand, level(shop.shirt).reserved) == (8, 0)
    assert sales(shop.shirt) == 1
    assert list(row.events.values_list("event", flat=True)).count("payment_confirmed") == 1
    assert attempts(order["reference"]).get().status == "success"
    assert inventory.verify_ledger(shop.shirt) == []


def test_two_payments_for_one_order_at_once_sell_once_and_flag_the_second(shop):
    order = place_order([(shop.shirt, 2)])
    references = [start_ok(order["reference"]) for _ in range(2)]
    responses = in_parallel(10, lambda i: verify_page(references[i % 2]))
    assert {r.status_code for r in responses} == {200}
    assert sorted(a.status for a in attempts(order["reference"])) == ["duplicate", "success"]
    assert sales(shop.shirt) == 1 and level(shop.shirt).on_hand == 8
    assert order_row(order["reference"]).payment == "paid"
    assert inventory.verify_ledger(shop.shirt) == []


@pytest.mark.parametrize(
    ("head_start", "who_wins"),
    [("payer", "payer"), ("buyer", "buyer")] + [("neither", None)] * 6,
)
def test_a_late_payer_and_a_new_buyer_cannot_both_get_the_last_unit(shop, head_start, who_wins):
    late = place_order([(shop.scarce, 1)], phone="0241230001")
    reference = start_ok(late["reference"])
    expire_holds(late["reference"])
    buyer_body = {
        "items": [{"variant_id": shop.scarce, "quantity": 1}],
        "delivery": {"method": "pickup"},
        "contact_name": "New Buyer",
        "contact_phone": "0249990000",
        "payment_method": "online",
    }

    def work(i):
        if (i == 0 and head_start == "buyer") or (i == 1 and head_start == "payer"):
            time.sleep(0.4)  # the other side gets a clear head start
        if i == 0:
            return ("pay", verify_page(reference).status_code)
        response = APIClient().post(
            "/api/v1/orders/", buyer_body, format="json", HTTP_IDEMPOTENCY_KEY="racing-buyer-key"
        )
        return ("buy", response.status_code)

    results = dict(in_parallel(2, work))
    assert results["pay"] == 200 and results["buy"] in (201, 409)
    if who_wins == "payer":
        assert results["buy"] == 409
    if who_wins == "buyer":
        assert results["buy"] == 201
    paid_late = order_row(late["reference"])
    assert paid_late.payment == "paid"
    stock = level(shop.scarce)
    if results["buy"] == 201:  # the new buyer was first: the late payer is refunded
        assert paid_late.fulfilment == "not_fulfillable" and paid_late.refund == "requested"
        assert (stock.on_hand, stock.reserved) == (1, 1) and sales(shop.scarce) == 0
    else:  # the late payer was first: the new buyer is told it is gone
        assert paid_late.fulfilment == "to_pack" and paid_late.refund == "none"
        assert (stock.on_hand, stock.reserved) == (0, 0) and sales(shop.scarce) == 1
    assert inventory.verify_ledger(shop.scarce) == []
