"""FIFO allocation and ledger consistency checks. Pure Python, no Django, no database.

The database layer (services.py) locks rows and writes. The decisions live here so they can be
tested exhaustively without a database.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from .errors import InsufficientStock


def allocate_fifo(
    batches: Sequence[tuple[int, int]], quantity: int, *, variant_id: int | None = None
) -> list[tuple[int, int]]:
    """Take `quantity` from batches, oldest first.

    `batches` is (batch_id, remaining) in oldest-first order. Returns (batch_id, taken) pairs:
    every taken amount is above zero and at most that batch's remaining, and they add up to
    `quantity`. Raises InsufficientStock if the batches cannot cover it. Never mutates input.
    """
    if quantity < 1:
        raise ValueError("quantity must be at least 1")
    plan: list[tuple[int, int]] = []
    needed = quantity
    for batch_id, remaining in batches:
        if remaining < 0:
            raise ValueError("a batch cannot have negative remaining stock")
        if needed == 0:
            break
        take = min(remaining, needed)
        if take > 0:
            plan.append((batch_id, take))
            needed -= take
    if needed:
        raise InsufficientStock(variant_id, quantity, quantity - needed)
    return plan


@dataclass(frozen=True)
class BatchRow:
    id: int
    received: int
    remaining: int


@dataclass(frozen=True)
class MovementRow:
    batch_id: int
    quantity: int  # positive in, negative out


@dataclass(frozen=True)
class LedgerSnapshot:
    on_hand: int
    reserved: int
    active_reserved: int  # sum of the quantities of reservations still active
    batches: Sequence[BatchRow]
    movements: Sequence[MovementRow]


def check_invariants(snapshot: LedgerSnapshot) -> list[str]:
    """Return a description of every rule the data breaks. Empty means consistent."""
    problems: list[str] = []
    moved = sum(m.quantity for m in snapshot.movements)
    if snapshot.on_hand != moved:
        problems.append(f"on_hand {snapshot.on_hand} != sum of movements {moved}")
    remaining = sum(b.remaining for b in snapshot.batches)
    if snapshot.on_hand != remaining:
        problems.append(f"on_hand {snapshot.on_hand} != sum of batch remaining {remaining}")
    by_batch: dict[int, int] = {}
    for movement in snapshot.movements:
        by_batch[movement.batch_id] = by_batch.get(movement.batch_id, 0) + movement.quantity
    known = {batch.id for batch in snapshot.batches}
    for batch_id in sorted(set(by_batch) - known):
        problems.append(f"movements point at unknown batch {batch_id}")
    for batch in snapshot.batches:
        expected = by_batch.get(batch.id, 0)
        if batch.remaining != expected:
            problems.append(f"batch {batch.id} remaining {batch.remaining} != movements {expected}")
        if not 0 <= batch.remaining <= batch.received:
            problems.append(f"batch {batch.id} remaining {batch.remaining} outside 0..received")
    if snapshot.reserved != snapshot.active_reserved:
        problems.append(
            f"reserved {snapshot.reserved} != active reservations {snapshot.active_reserved}"
        )
    if snapshot.on_hand < 0:
        problems.append("on_hand is negative")
    if not 0 <= snapshot.reserved <= snapshot.on_hand:
        problems.append(f"reserved {snapshot.reserved} outside 0..on_hand {snapshot.on_hand}")
    return problems
