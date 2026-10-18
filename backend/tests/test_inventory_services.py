from datetime import timedelta

import pytest
from django.utils import timezone

from apps.inventory.errors import IdempotencyConflict, InsufficientStock, ReservationNotActive
from apps.inventory.models import (
    Batch,
    MovementKind,
    Reservation,
    ReservationStatus,
    StockLevel,
    StockMovement,
)
from apps.inventory.services import (
    StockRequest,
    available,
    confirm_sale,
    expire_overdue,
    receive_stock,
    release,
    reserve_many,
    verify_ledger,
)

V = 101
W = 202


def stock(quantity, key, variant=V, **kwargs):
    return receive_stock(variant, quantity, idempotency_key=key, **kwargs)


def hold(quantity, key, variant=V, **kwargs):
    (reservation,) = reserve_many([StockRequest(variant, quantity)], idempotency_key=key, **kwargs)
    return reservation


def level(variant=V):
    return StockLevel.objects.get(variant_id=variant)


# --- receiving -------------------------------------------------------------------


@pytest.mark.django_db
def test_receiving_writes_a_batch_a_movement_and_the_cache():
    batch = stock(10, "r1", unit_cost_pesewas=4500)
    assert (batch.quantity_received, batch.quantity_remaining, batch.unit_cost_pesewas) == (
        10,
        10,
        4500,
    )
    movement = StockMovement.objects.get()
    assert (movement.kind, movement.quantity, movement.batch_id) == (
        MovementKind.RECEIPT,
        10,
        batch.id,
    )
    assert level().on_hand == 10
    assert verify_ledger(V) == []


@pytest.mark.django_db
def test_receiving_twice_with_the_same_key_adds_stock_once():
    first = stock(10, "r1")
    second = stock(10, "r1")
    assert first.id == second.id
    assert (Batch.objects.count(), StockMovement.objects.count(), level().on_hand) == (1, 1, 10)


@pytest.mark.django_db
def test_reusing_a_receipt_key_for_something_else_is_refused():
    stock(10, "r1")
    with pytest.raises(IdempotencyConflict):
        stock(11, "r1")
    with pytest.raises(IdempotencyConflict):
        stock(10, "r1", variant=W)


@pytest.mark.django_db
def test_receiving_nothing_is_refused():
    with pytest.raises(ValueError):
        stock(0, "r1")


# --- reserving -------------------------------------------------------------------


@pytest.mark.django_db
def test_a_hold_reduces_what_can_be_sold_but_not_what_is_on_hand():
    stock(10, "r1")
    hold(4, "c1")
    assert (level().on_hand, level().reserved) == (10, 4)
    assert available([V]) == {V: 6}


@pytest.mark.django_db
def test_holding_more_than_is_available_is_refused_and_holds_nothing():
    stock(3, "r1")
    with pytest.raises(InsufficientStock) as caught:
        hold(4, "c1")
    assert (caught.value.variant_id, caught.value.requested, caught.value.available) == (V, 4, 3)
    assert Reservation.objects.count() == 0 and level().reserved == 0


@pytest.mark.django_db
def test_holding_a_variant_that_never_had_stock_is_refused():
    with pytest.raises(InsufficientStock) as caught:
        hold(1, "c1")
    assert caught.value.available == 0


@pytest.mark.django_db
def test_a_cart_is_held_completely_or_not_at_all():
    stock(5, "r1", variant=V)
    stock(1, "r2", variant=W)
    with pytest.raises(InsufficientStock) as caught:
        reserve_many([StockRequest(V, 2), StockRequest(W, 2)], idempotency_key="c1")
    assert caught.value.variant_id == W
    assert level(V).reserved == 0 and level(W).reserved == 0
    assert Reservation.objects.count() == 0


@pytest.mark.django_db
def test_reserving_twice_with_the_same_key_holds_once():
    stock(10, "r1")
    first = hold(3, "c1")
    second = hold(3, "c1")
    assert first.id == second.id
    assert level().reserved == 3


@pytest.mark.django_db
def test_reusing_a_cart_key_for_a_different_cart_is_refused():
    stock(10, "r1")
    hold(3, "c1")
    with pytest.raises(IdempotencyConflict):
        hold(4, "c1")


@pytest.mark.django_db
def test_the_same_variant_twice_in_one_cart_is_a_programming_error():
    stock(10, "r1")
    with pytest.raises(ValueError):
        reserve_many([StockRequest(V, 1), StockRequest(V, 1)], idempotency_key="c1")


@pytest.mark.django_db
def test_reservations_come_back_in_the_order_the_items_were_given():
    stock(5, "r1", variant=V)
    stock(5, "r2", variant=W)
    held = reserve_many([StockRequest(W, 1), StockRequest(V, 2)], idempotency_key="c1")
    assert [r.variant_id for r in held] == [W, V]


# --- releasing and expiring --------------------------------------------------------


@pytest.mark.django_db
def test_releasing_gives_the_stock_back_and_is_safe_to_repeat():
    stock(10, "r1")
    reservation = hold(4, "c1")
    assert release([reservation.id]) == 1
    assert release([reservation.id]) == 0
    assert level().reserved == 0
    assert Reservation.objects.get().status == ReservationStatus.RELEASED


@pytest.mark.django_db
def test_holds_expire_after_fifteen_minutes_and_not_before():
    stock(10, "r1")
    start = timezone.now()
    hold(4, "c1", now=start)
    assert expire_overdue(now=start + timedelta(minutes=14)) == 0
    assert level().reserved == 4
    assert expire_overdue(now=start + timedelta(minutes=16)) == 1
    assert level().reserved == 0
    assert Reservation.objects.get().status == ReservationStatus.EXPIRED
    assert expire_overdue(now=start + timedelta(minutes=60)) == 0
    assert verify_ledger(V) == []


@pytest.mark.django_db
def test_expired_stock_can_be_bought_by_someone_else():
    stock(1, "r1")
    start = timezone.now()
    hold(1, "slow-buyer", now=start)
    with pytest.raises(InsufficientStock):
        hold(1, "other-buyer", now=start)
    expire_overdue(now=start + timedelta(minutes=16))
    assert hold(1, "other-buyer").status == ReservationStatus.ACTIVE


# --- selling -----------------------------------------------------------------------


@pytest.mark.django_db
def test_a_sale_takes_the_oldest_batch_first_by_received_date_not_insertion_order():
    now = timezone.now()
    newer = stock(5, "new", received_at=now - timedelta(days=1))  # entered first
    older = stock(3, "old", received_at=now - timedelta(days=9))  # entered second, but older
    reservation = hold(4, "c1")
    confirm_sale([reservation.id])
    older.refresh_from_db()
    newer.refresh_from_db()
    assert (older.quantity_remaining, newer.quantity_remaining) == (0, 4)
    sales = StockMovement.objects.filter(kind=MovementKind.SALE).order_by("id")
    assert [(m.batch_id, m.quantity) for m in sales] == [(older.id, -3), (newer.id, -1)]
    assert (level().on_hand, level().reserved) == (4, 0)
    assert Reservation.objects.get().status == ReservationStatus.CONFIRMED
    assert verify_ledger(V) == []


@pytest.mark.django_db
def test_confirming_twice_sells_once():
    stock(10, "r1")
    reservation = hold(4, "c1")
    confirm_sale([reservation.id])
    confirm_sale([reservation.id])
    assert StockMovement.objects.filter(kind=MovementKind.SALE).count() == 1
    assert level().on_hand == 6
    assert verify_ledger(V) == []


@pytest.mark.django_db
def test_a_whole_cart_is_confirmed_together():
    stock(5, "r1", variant=V)
    stock(5, "r2", variant=W)
    held = reserve_many([StockRequest(W, 2), StockRequest(V, 3)], idempotency_key="c1")
    confirm_sale([r.id for r in held])
    assert (level(V).on_hand, level(W).on_hand) == (2, 3)
    assert verify_ledger(V) == [] and verify_ledger(W) == []


@pytest.mark.django_db
def test_an_expired_hold_cannot_be_sold_and_nothing_changes():
    stock(10, "r1")
    start = timezone.now()
    reservation = hold(4, "c1", now=start)
    expire_overdue(now=start + timedelta(minutes=16))
    with pytest.raises(ReservationNotActive) as caught:
        confirm_sale([reservation.id])
    assert caught.value.status == ReservationStatus.EXPIRED
    assert StockMovement.objects.filter(kind=MovementKind.SALE).count() == 0
    assert level().on_hand == 10


@pytest.mark.django_db
def test_one_bad_hold_in_a_cart_stops_the_whole_confirmation():
    stock(5, "r1", variant=V)
    stock(5, "r2", variant=W)
    good = hold(1, "c1", variant=V)
    bad = hold(1, "c2", variant=W)
    release([bad.id])
    with pytest.raises(ReservationNotActive):
        confirm_sale([good.id, bad.id])
    assert level(V).on_hand == 5
    assert Reservation.objects.get(id=good.id).status == ReservationStatus.ACTIVE


@pytest.mark.django_db
def test_available_counts_unknown_variants_as_zero():
    stock(5, "r1")
    hold(2, "c1")
    assert available([V, 999]) == {V: 3, 999: 0}
