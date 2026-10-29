"""Simultaneous checkouts on a real PostgreSQL database. These prove what code alone cannot: the
last unit sells once, a retry stampede makes one order, and no number gets past its limit."""

import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import pytest
from django.db import connection, connections
from rest_framework.test import APIClient

from apps.inventory import services as inventory
from apps.inventory.models import Reservation, StockLevel
from apps.orders.models import Order, OrderLine, OrderReservation

pytestmark = pytest.mark.django_db(transaction=True)

URL = "/api/v1/orders/"


def phone(n: int) -> str:
    return f"024123{n:04d}"


def body(items, *, number=0, name="Ama Mensah"):
    return {
        "items": [{"variant_id": v, "quantity": q} for v, q in items],
        "delivery": {"method": "pickup"},
        "contact_name": name,
        "contact_phone": phone(number),
        "payment_method": "online",
    }


def place(data, key):
    return APIClient().post(URL, data, format="json", HTTP_IDEMPOTENCY_KEY=key)


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


def reserved(variant_id):
    return StockLevel.objects.get(variant_id=variant_id).reserved


def test_the_database_runs_postgresql():
    assert connection.vendor == "postgresql"


def test_the_last_unit_goes_to_exactly_one_of_many_buyers(shop):
    responses = in_parallel(
        20, lambda i: place(body([(shop.scarce, 1)], number=i), f"buyer-key-{i:04d}")
    )
    assert Counter(r.status_code for r in responses) == {201: 1, 409: 19}
    assert Order.objects.count() == 1 and reserved(shop.scarce) == 1
    assert Reservation.objects.count() == 1 and OrderReservation.objects.count() == 1
    assert inventory.verify_ledger(shop.scarce) == []


def test_a_stampede_of_retries_makes_one_order_and_one_hold(shop):
    responses = in_parallel(15, lambda i: place(body([(shop.shirt, 2)]), "one-key-for-all"))
    assert Counter(r.status_code for r in responses) == {201: 1, 200: 14}
    assert len({r.json()["reference"] for r in responses}) == 1
    assert Order.objects.count() == 1 and Reservation.objects.count() == 1
    assert OrderReservation.objects.count() == 1 and reserved(shop.shirt) == 2
    assert inventory.verify_ledger(shop.shirt) == []


def test_one_key_used_for_different_requests_at_once_makes_one_order(shop):
    def work(i):
        # half ask for 2 shirts, half for 3 shirts and a pair of shoes
        items = [(shop.shirt, 2)] if i % 2 else [(shop.shirt, 3), (shop.shoe, 1)]
        return place(body(items), "contested-key-1")

    responses = in_parallel(16, work)
    counts = Counter(r.status_code for r in responses)
    assert counts[201] == 1 and set(counts) <= {201, 200, 409}
    assert Order.objects.count() == 1
    order = Order.objects.get()
    expected = {line.variant_id: line.quantity for line in order.lines.all()}
    assert {r.variant_id: r.quantity for r in Reservation.objects.all()} == expected
    assert reserved(shop.shirt) == expected[shop.shirt]
    assert reserved(shop.shoe) == expected.get(shop.shoe, 0)
    assert inventory.verify_ledger(shop.shirt) == [] and inventory.verify_ledger(shop.shoe) == []


def test_one_number_cannot_get_past_its_open_order_limit_by_racing(shop, settings):
    settings.CHECKOUT_LIMITS = {"open_orders_per_phone": 3, "checkout_ip_rate": "10000/hour"}
    responses = in_parallel(
        12, lambda i: place(body([(shop.shirt, 1)], number=7), f"same-phone-{i:04d}")
    )
    assert Counter(r.status_code for r in responses) == {201: 3, 429: 9}
    assert Order.objects.count() == 3 and reserved(shop.shirt) == 3


def test_many_buyers_of_two_items_in_either_order_never_oversell_or_deadlock(shop):
    def work(i):
        items = [(shop.shirt, 1), (shop.shoe, 1)] if i % 2 else [(shop.shoe, 1), (shop.shirt, 1)]
        return place(body(items, number=i), f"pair-key-{i:04d}")

    responses = in_parallel(30, work)
    counts = Counter(r.status_code for r in responses)
    assert counts == {201: 4, 409: 26}  # four pairs of shoes in stock, ten shirts
    assert reserved(shop.shoe) == 4 and reserved(shop.shirt) == 4
    assert OrderLine.objects.filter(variant_id=shop.shoe).count() == 4
    assert inventory.verify_ledger(shop.shirt) == [] and inventory.verify_ledger(shop.shoe) == []


def test_buyers_for_different_items_do_not_block_each_other(shop):
    def work(i):
        variant = shop.shirt if i % 2 else shop.shoe
        return place(body([(variant, 1)], number=i), f"mixed-key-{i:04d}")

    responses = in_parallel(8, work)
    assert [r.status_code for r in responses] == [201] * 8
    assert reserved(shop.shirt) == 4 and reserved(shop.shoe) == 4


def test_a_retry_stampede_is_never_mistaken_for_a_pile_of_new_orders(shop, settings):
    settings.CHECKOUT_LIMITS = {"open_orders_per_phone": 1, "checkout_ip_rate": "10000/hour"}
    responses = in_parallel(
        15, lambda i: place(body([(shop.shirt, 1)], number=5), "retry-key-0001")
    )
    assert Counter(r.status_code for r in responses) == {201: 1, 200: 14}
    assert Order.objects.count() == 1 and reserved(shop.shirt) == 1


@pytest.mark.parametrize("other_quantity", [2, 3])
def test_one_key_arriving_from_different_numbers_at_once_makes_one_order(shop, other_quantity):
    def work(i):
        quantity = 2 if i % 2 == 0 else other_quantity
        return place(body([(shop.shirt, quantity)], number=i), "shared-contested-key")

    responses = in_parallel(12, work)
    counts = Counter(r.status_code for r in responses)
    assert counts == {201: 1, 409: 11}  # nobody gets a 500, and nobody gets a second order
    assert all(
        r.json()["error"]["details"]["reason"] == "idempotency_conflict"
        for r in responses
        if r.status_code == 409
    )
    order = Order.objects.get()
    quantity = order.lines.get().quantity
    assert Reservation.objects.count() == 1 and OrderReservation.objects.count() == 1
    assert reserved(shop.shirt) == quantity
    assert inventory.verify_ledger(shop.shirt) == []
