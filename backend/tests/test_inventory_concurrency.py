import threading

import pytest
from django.db import connections

from apps.inventory.errors import InsufficientStock
from apps.inventory.models import Batch, MovementKind, StockLevel, StockMovement
from apps.inventory.services import (
    StockRequest,
    confirm_sale,
    receive_stock,
    reserve_many,
    verify_ledger,
)

V = 301
W = 302


def run_in_parallel(count, work):
    """Run work(i) on `count` threads released at the same moment. Returns (status, value)."""
    barrier = threading.Barrier(count)
    results = [None] * count

    def worker(i):
        try:
            barrier.wait(timeout=20)
            results[i] = ("ok", work(i))
        except Exception as error:  # reported to the test, not swallowed
            results[i] = ("error", error)
        finally:
            connections.close_all()  # each thread opened its own connection

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert not any(thread.is_alive() for thread in threads), "a thread is stuck (deadlock?)"
    return results


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(("units", "buyers"), [(1, 2), (1, 10), (3, 8)])
def test_buyers_never_get_more_than_the_stock(units, buyers):
    receive_stock(V, units, idempotency_key="r1")

    def buy(i):
        return reserve_many([StockRequest(V, 1)], idempotency_key=f"buyer-{i}")

    results = run_in_parallel(buyers, buy)
    wins = [r for r in results if r[0] == "ok"]
    refused = [r for r in results if r[0] == "error" and isinstance(r[1], InsufficientStock)]
    refused_ids = {id(r) for r in refused}
    other_errors = [r for r in results if r[0] == "error" and id(r) not in refused_ids]
    assert not other_errors, other_errors
    assert len(wins) == units
    assert len(refused) == buyers - units
    assert StockLevel.objects.get(variant_id=V).reserved == units
    assert verify_ledger(V) == []


@pytest.mark.django_db(transaction=True)
def test_the_same_hold_confirmed_by_two_requests_at_once_sells_once():
    receive_stock(V, 5, idempotency_key="r1")
    (reservation,) = reserve_many([StockRequest(V, 2)], idempotency_key="c1")

    results = run_in_parallel(2, lambda i: confirm_sale([reservation.id]))
    assert [r[0] for r in results] == ["ok", "ok"], results
    assert StockMovement.objects.filter(kind=MovementKind.SALE).count() == 1
    assert StockLevel.objects.get(variant_id=V).on_hand == 3
    assert verify_ledger(V) == []


@pytest.mark.django_db(transaction=True)
def test_carts_listing_the_same_variants_in_opposite_order_do_not_deadlock():
    receive_stock(V, 500, idempotency_key="r1")
    receive_stock(W, 500, idempotency_key="r2")

    def shop(i):
        items = [StockRequest(V, 1), StockRequest(W, 1)]
        if i % 2:
            items.reverse()
        for turn in range(15):
            reserve_many(items, idempotency_key=f"worker-{i}-turn-{turn}")

    results = run_in_parallel(6, shop)
    assert [r[0] for r in results] == ["ok"] * 6, results
    assert StockLevel.objects.get(variant_id=V).reserved == 6 * 15
    assert verify_ledger(V) == [] and verify_ledger(W) == []


@pytest.mark.django_db(transaction=True)
def test_the_same_receipt_arriving_twice_at_once_creates_one_batch():
    results = run_in_parallel(4, lambda i: receive_stock(V, 10, idempotency_key="same-delivery"))
    assert [r[0] for r in results] == ["ok"] * 4, results
    assert Batch.objects.count() == 1
    assert StockLevel.objects.get(variant_id=V).on_hand == 10
    assert verify_ledger(V) == []
