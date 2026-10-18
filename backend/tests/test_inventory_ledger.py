import random
from datetime import timedelta

import pytest
from django.db import DatabaseError, IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from apps.inventory.errors import InsufficientStock, ReservationNotActive
from apps.inventory.models import Reservation, ReservationStatus, StockLevel, StockMovement
from apps.inventory.services import (
    StockRequest,
    confirm_sale,
    expire_overdue,
    receive_stock,
    release,
    reserve_many,
    verify_ledger,
)

V = 401


@pytest.mark.django_db
def test_the_database_itself_refuses_negative_stock():
    receive_stock(V, 5, idempotency_key="r1")
    with pytest.raises(IntegrityError), transaction.atomic():
        StockLevel.objects.filter(variant_id=V).update(on_hand=F("on_hand") - 6)


@pytest.mark.django_db
def test_the_database_refuses_more_held_than_on_hand():
    receive_stock(V, 5, idempotency_key="r1")
    with pytest.raises(IntegrityError), transaction.atomic():
        StockLevel.objects.filter(variant_id=V).update(reserved=6)


@pytest.mark.django_db
def test_stock_movements_cannot_be_updated_or_deleted():
    receive_stock(V, 5, idempotency_key="r1")
    with pytest.raises(DatabaseError), transaction.atomic():
        StockMovement.objects.update(quantity=99)
    with pytest.raises(DatabaseError), transaction.atomic():
        StockMovement.objects.all().delete()
    assert StockMovement.objects.get().quantity == 5


@pytest.mark.django_db
def test_a_zero_movement_is_refused_by_the_database():
    batch = receive_stock(V, 5, idempotency_key="r1")
    with pytest.raises(IntegrityError), transaction.atomic():
        StockMovement.objects.create(
            variant_id=V, batch=batch, kind="sale", quantity=0, idempotency_key="x"
        )


@pytest.mark.django_db
def test_verify_ledger_reports_a_cache_that_was_tampered_with():
    receive_stock(V, 5, idempotency_key="r1")
    assert verify_ledger(V) == []
    StockLevel.objects.filter(variant_id=V).update(on_hand=4)
    assert verify_ledger(V)


@pytest.mark.django_db
@pytest.mark.parametrize("seed", range(6))
def test_a_long_random_history_keeps_every_rule(seed):
    rng = random.Random(seed)
    clock = timezone.now()
    holds = []
    for step in range(60):
        action = rng.choice(["receive", "reserve", "reserve", "release", "confirm", "expire"])
        if action == "receive":
            receive_stock(V, rng.randint(1, 8), idempotency_key=f"r-{seed}-{step}")
        elif action == "reserve":
            try:
                (hold,) = reserve_many(
                    [StockRequest(V, rng.randint(1, 6))],
                    idempotency_key=f"c-{seed}-{step}",
                    now=clock,
                )
                holds.append(hold.id)
            except InsufficientStock as error:
                assert error.available < error.requested
        elif action == "release" and holds:
            release([rng.choice(holds)])
        elif action == "confirm" and holds:
            try:
                confirm_sale([rng.choice(holds)])
            except ReservationNotActive:
                pass
        elif action == "expire":
            clock += timedelta(minutes=rng.randint(1, 10))
            expire_overdue(now=clock)
        assert verify_ledger(V) == [], (seed, step, action)
    level = StockLevel.objects.get(variant_id=V)
    assert 0 <= level.reserved <= level.on_hand
    still_active = Reservation.objects.filter(status=ReservationStatus.ACTIVE)
    assert sum(r.quantity for r in still_active) == level.reserved
