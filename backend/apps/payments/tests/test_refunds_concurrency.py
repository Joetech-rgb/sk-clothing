"""Simultaneous refund runs on a real PostgreSQL database: however many runners overlap, each
payment is refunded once."""

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from django.db import connection, connections

from apps.payments import refunds
from apps.payments.models import Refund
from apps.payments.tests.helpers import fake, order_row, refund_requested_order

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


def test_the_database_runs_postgresql():
    assert connection.vendor == "postgresql"


def test_many_runners_at_once_create_and_send_one_refund(shop):
    order, reference = refund_requested_order(shop)
    in_parallel(10, lambda i: refunds.process_refunds(fake()))
    assert Refund.objects.count() == 1
    assert len(fake().refund_calls) == 1 and len(fake().refunds) == 1
    refund = Refund.objects.get()
    assert refund.status == "submitted" and refund.attempts == 1
    assert order_row(order["reference"]).refund == "submitted"


def test_many_runners_sending_the_same_refund_send_it_once(shop):
    _, reference = refund_requested_order(shop)
    refunds.queue_refunds()
    refund = Refund.objects.get()
    outcomes = in_parallel(10, lambda i: refunds.submit_refund(refund.pk, fake()))
    assert outcomes.count(refunds.SKIPPED) == 9
    assert len(fake().refund_calls) == 1 and Refund.objects.get().attempts == 1


def test_many_runners_queueing_at_once_make_one_refund_per_payment(shop):
    refund_requested_order(shop)
    created = in_parallel(10, lambda i: refunds.queue_refunds())
    assert sum(created) == 1 and Refund.objects.count() == 1


def test_a_dozen_refunds_with_overlapping_runners_each_go_out_exactly_once(shop):
    references = []
    for n in range(12):
        # each late payer finds the unit gone: stock for each is its own variant
        from apps.catalog.models import PriceTier, Product, Variant
        from apps.inventory import services as inventory
        from apps.payments.tests.helpers import (
            expire_holds,
            place_order,
            start_ok,
            verify_page,
        )

        variant = Variant.objects.create(
            product=Product.objects.get(slug="red-shirt"), sku=f"R-{n}", size=f"S{n}"
        )
        PriceTier.objects.create(variant=variant, tier="retail", price_pesewas=1000 + n)
        inventory.receive_stock(variant.pk, 1, idempotency_key=f"seed-r-{n}")
        order = place_order([(variant.pk, 1)], phone=f"024123{n:04d}")
        reference = start_ok(order["reference"])
        expire_holds(order["reference"])
        place_order([(variant.pk, 1)], phone="0249990000")
        assert verify_page(reference).json()["outcome"] == "paid_not_fulfillable"
        references.append(reference)
    in_parallel(6, lambda i: refunds.process_refunds(fake()))
    assert Refund.objects.count() == 12
    assert sorted(c["transaction"] for c in fake().refund_calls) == sorted(references)
    assert set(Refund.objects.values_list("status", flat=True)) == {"submitted"}
