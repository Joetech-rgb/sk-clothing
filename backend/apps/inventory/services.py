"""Stock services. The only code allowed to change stock.

Rules (CLAUDE.md section 4):
- Stock is the sum of append-only StockMovement rows. StockLevel and Batch.quantity_remaining
  are caches written in the same transaction as the movement.
- Every change locks the variant's StockLevel row first (select_for_update inside atomic), and
  anything touching several variants locks them in ascending variant_id order, so two buyers
  can never both take the last unit and two orders can never deadlock each other.
- Reservations expire after 15 minutes. Sales consume the oldest batch first.
- Every write that can be retried takes an idempotency key and is safe to repeat.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.db import transaction
from django.utils import timezone

from .allocation import BatchRow, LedgerSnapshot, MovementRow, allocate_fifo, check_invariants
from .errors import IdempotencyConflict, InsufficientStock, ReservationNotActive
from .models import (
    Batch,
    MovementKind,
    Reservation,
    ReservationStatus,
    StockLevel,
    StockMovement,
)

RESERVATION_TTL = timedelta(minutes=15)


@dataclass(frozen=True)
class StockRequest:
    variant_id: int
    quantity: int


def _lock_levels(variant_ids: Iterable[int], *, create: bool = False) -> dict[int, StockLevel]:
    """Lock the StockLevel rows in ascending variant_id order. Call inside atomic()."""
    ordered = sorted(set(variant_ids))
    if create:
        for variant_id in ordered:
            StockLevel.objects.get_or_create(variant_id=variant_id)
    rows = StockLevel.objects.select_for_update().filter(variant_id__in=ordered)
    return {level.variant_id: level for level in rows.order_by("variant_id")}


def receive_stock(
    variant_id: int,
    quantity: int,
    *,
    idempotency_key: str,
    unit_cost_pesewas: int | None = None,
    received_at: datetime | None = None,
) -> Batch:
    """Add a batch. Repeating the same key returns the same batch and adds nothing."""
    if quantity < 1:
        raise ValueError("quantity must be at least 1")
    with transaction.atomic():
        level = _lock_levels([variant_id], create=True)[variant_id]
        existing = Batch.objects.filter(idempotency_key=idempotency_key).first()
        if existing is not None:
            if existing.variant_id != variant_id or existing.quantity_received != quantity:
                raise IdempotencyConflict(f"key {idempotency_key!r} was used for another receipt")
            return existing
        batch = Batch.objects.create(
            variant_id=variant_id,
            quantity_received=quantity,
            quantity_remaining=quantity,
            unit_cost_pesewas=unit_cost_pesewas,
            received_at=received_at or timezone.now(),
            idempotency_key=idempotency_key,
        )
        StockMovement.objects.create(
            variant_id=variant_id,
            batch=batch,
            kind=MovementKind.RECEIPT,
            quantity=quantity,
            idempotency_key=idempotency_key,
        )
        level.on_hand += quantity
        level.save(update_fields=["on_hand", "updated_at"])
        return batch


def reserve_many(
    items: Sequence[StockRequest],
    *,
    idempotency_key: str,
    ttl: timedelta = RESERVATION_TTL,
    now: datetime | None = None,
) -> list[Reservation]:
    """Hold every item or none of them. Returns reservations in the order of `items`.

    Raises InsufficientStock for the first variant that cannot be covered, and nothing is held.
    Repeating the same key returns the existing holds, whatever their status now is.
    """
    if not items:
        return []
    variant_ids = [item.variant_id for item in items]
    if len(set(variant_ids)) != len(variant_ids):
        raise ValueError("each variant may appear once; add the quantities together first")
    if any(item.quantity < 1 for item in items):
        raise ValueError("quantity must be at least 1")
    expires_at = (now or timezone.now()) + ttl

    with transaction.atomic():
        levels = _lock_levels(variant_ids)
        held: dict[int, Reservation] = {}
        for item in sorted(items, key=lambda i: i.variant_id):
            key = f"{idempotency_key}:{item.variant_id}"
            existing = Reservation.objects.filter(idempotency_key=key).first()
            if existing is not None:
                if existing.quantity != item.quantity:
                    raise IdempotencyConflict(f"key {idempotency_key!r} was used for another cart")
                held[item.variant_id] = existing
                continue
            level = levels.get(item.variant_id)
            available = level.on_hand - level.reserved if level else 0
            if level is None or available < item.quantity:
                raise InsufficientStock(item.variant_id, item.quantity, available)
            held[item.variant_id] = Reservation.objects.create(
                variant_id=item.variant_id,
                quantity=item.quantity,
                idempotency_key=key,
                expires_at=expires_at,
            )
            level.reserved += item.quantity
            level.save(update_fields=["reserved", "updated_at"])
        return [held[item.variant_id] for item in items]


def _load_locked(reservation_ids: Iterable[int]) -> tuple[dict[int, StockLevel], list[Reservation]]:
    """Lock levels first, then the reservations, in a fixed order. Call inside atomic()."""
    ids = sorted(set(reservation_ids))
    variant_ids = Reservation.objects.filter(id__in=ids).values_list("variant_id", flat=True)
    levels = _lock_levels(variant_ids)
    reservations = list(
        Reservation.objects.select_for_update().filter(id__in=ids).order_by("variant_id", "id")
    )
    return levels, reservations


def _release(reservation_ids: Iterable[int], final: ReservationStatus) -> int:
    changed = 0
    with transaction.atomic():
        levels, reservations = _load_locked(reservation_ids)
        for reservation in reservations:
            if reservation.status != ReservationStatus.ACTIVE:
                continue  # already confirmed, released or expired: nothing to undo
            level = levels[reservation.variant_id]
            level.reserved -= reservation.quantity
            level.save(update_fields=["reserved", "updated_at"])
            reservation.status = final
            reservation.save(update_fields=["status"])
            changed += 1
    return changed


def release(reservation_ids: Iterable[int]) -> int:
    """Give held stock back (customer left, payment failed). Safe to repeat."""
    return _release(reservation_ids, ReservationStatus.RELEASED)


def expire_overdue(now: datetime | None = None, batch_size: int = 500) -> int:
    """Release every active hold past its expiry. Run every minute by Celery Beat."""
    cutoff = now or timezone.now()
    total = 0
    while True:
        ids = list(
            Reservation.objects.filter(status=ReservationStatus.ACTIVE, expires_at__lte=cutoff)
            .order_by("id")
            .values_list("id", flat=True)[:batch_size]
        )
        if not ids:
            return total
        total += _release(ids, ReservationStatus.EXPIRED)


def confirm_sale(reservation_ids: Iterable[int]) -> list[Reservation]:
    """Turn holds into sales: write SALE movements oldest batch first. Safe to repeat.

    A hold that expired or was released raises ReservationNotActive and nothing at all is
    changed. What to do then (re-reserve, refund) is a business decision for the orders layer.
    """
    with transaction.atomic():
        levels, reservations = _load_locked(reservation_ids)
        for reservation in reservations:
            if reservation.status not in (ReservationStatus.ACTIVE, ReservationStatus.CONFIRMED):
                raise ReservationNotActive(reservation.pk, reservation.status)
        for reservation in reservations:
            if reservation.status == ReservationStatus.CONFIRMED:
                continue  # replay
            level = levels[reservation.variant_id]
            batches = list(
                Batch.objects.select_for_update()
                .filter(variant_id=reservation.variant_id, quantity_remaining__gt=0)
                .order_by("received_at", "id")
            )
            plan = allocate_fifo(
                [(b.pk, b.quantity_remaining) for b in batches],
                reservation.quantity,
                variant_id=reservation.variant_id,
            )
            by_id = {b.pk: b for b in batches}
            for batch_id, taken in plan:
                batch = by_id[batch_id]
                batch.quantity_remaining -= taken
                batch.save(update_fields=["quantity_remaining"])
                StockMovement.objects.create(
                    variant_id=reservation.variant_id,
                    batch=batch,
                    kind=MovementKind.SALE,
                    quantity=-taken,
                    idempotency_key=f"sale:{reservation.pk}",
                    reservation=reservation,
                )
            level.on_hand -= reservation.quantity
            level.reserved -= reservation.quantity
            level.save(update_fields=["on_hand", "reserved", "updated_at"])
            reservation.status = ReservationStatus.CONFIRMED
            reservation.save(update_fields=["status"])
        return reservations


def available(variant_ids: Iterable[int]) -> dict[int, int]:
    """Units that can be sold right now (on hand minus held). Missing variants count as 0."""
    ids = set(variant_ids)
    result = dict.fromkeys(ids, 0)
    for level in StockLevel.objects.filter(variant_id__in=ids):
        result[level.variant_id] = level.on_hand - level.reserved
    return result


def verify_ledger(variant_id: int) -> list[str]:
    """Check one variant's caches against its movements. Empty list means consistent."""
    level = StockLevel.objects.filter(variant_id=variant_id).first()
    if level is None:
        return []
    held = sum(
        quantity
        for quantity in Reservation.objects.filter(
            variant_id=variant_id, status=ReservationStatus.ACTIVE
        ).values_list("quantity", flat=True)
    )
    snapshot = LedgerSnapshot(
        on_hand=level.on_hand,
        reserved=level.reserved,
        active_reserved=held,
        batches=[
            BatchRow(b.pk, b.quantity_received, b.quantity_remaining)
            for b in Batch.objects.filter(variant_id=variant_id)
        ],
        movements=[
            MovementRow(batch_id, quantity)
            for batch_id, quantity in StockMovement.objects.filter(
                variant_id=variant_id
            ).values_list("batch_id", "quantity")
        ],
    )
    return check_invariants(snapshot)
