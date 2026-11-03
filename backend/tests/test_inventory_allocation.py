import random

import pytest
from hypothesis import given
from hypothesis import strategies as st

from apps.inventory.allocation import (
    BatchRow,
    LedgerSnapshot,
    MovementRow,
    allocate_fifo,
    check_invariants,
)
from apps.inventory.errors import InsufficientStock

# --- allocate_fifo -----------------------------------------------------------------


def test_takes_from_the_oldest_batch_first():
    assert allocate_fifo([(1, 5), (2, 5)], 3) == [(1, 3)]


def test_spills_into_the_next_batch_in_order():
    assert allocate_fifo([(1, 2), (2, 5), (3, 9)], 6) == [(1, 2), (2, 4)]


def test_exact_total_uses_every_batch():
    assert allocate_fifo([(1, 2), (2, 3)], 5) == [(1, 2), (2, 3)]


def test_empty_batches_are_skipped():
    assert allocate_fifo([(1, 0), (2, 4)], 3) == [(2, 3)]


def test_not_enough_stock_raises_with_the_amount_available():
    with pytest.raises(InsufficientStock) as caught:
        allocate_fifo([(1, 2), (2, 1)], 4, variant_id=9)
    assert (caught.value.variant_id, caught.value.requested, caught.value.available) == (9, 4, 3)


def test_no_batches_means_nothing_available():
    with pytest.raises(InsufficientStock) as caught:
        allocate_fifo([], 1)
    assert caught.value.available == 0


def test_bad_input_is_a_programming_error():
    with pytest.raises(ValueError):
        allocate_fifo([(1, 5)], 0)
    with pytest.raises(ValueError):
        allocate_fifo([(1, -1)], 1)


def test_input_is_not_mutated():
    batches = [(1, 2), (2, 5)]
    allocate_fifo(batches, 4)
    assert batches == [(1, 2), (2, 5)]


remaining = st.integers(min_value=0, max_value=50)


@given(
    a=remaining, b=remaining, c=remaining, d=remaining, want=st.integers(min_value=1, max_value=250)
)
def test_allocation_is_exact_ordered_and_within_each_batch(a, b, c, d, want):
    batches = list(enumerate([a, b, c, d], start=1))
    total = a + b + c + d
    if want > total:
        with pytest.raises(InsufficientStock):
            allocate_fifo(batches, want)
        return
    plan = allocate_fifo(batches, want)
    assert sum(take for _, take in plan) == want
    limits = dict(batches)
    assert all(0 < take <= limits[batch_id] for batch_id, take in plan)
    ids = [batch_id for batch_id, _ in plan]
    assert ids == sorted(ids)  # oldest first
    # FIFO: every batch before the last one used is drained completely.
    for batch_id, take in plan[:-1]:
        assert take == limits[batch_id]


# --- check_invariants --------------------------------------------------------------


def snapshot(**overrides):
    base = {
        "on_hand": 7,
        "reserved": 2,
        "active_reserved": 2,
        "batches": [BatchRow(1, 10, 3), BatchRow(2, 4, 4)],
        "movements": [MovementRow(1, 10), MovementRow(1, -7), MovementRow(2, 4)],
    }
    base.update(overrides)
    return LedgerSnapshot(**base)


def test_a_consistent_ledger_has_no_problems():
    assert check_invariants(snapshot()) == []


def test_each_kind_of_corruption_is_reported():
    assert check_invariants(snapshot(on_hand=8))  # cache disagrees with the movements
    assert check_invariants(snapshot(reserved=3))  # reserved disagrees with active holds
    assert check_invariants(snapshot(reserved=9, active_reserved=9))  # more held than on hand
    assert check_invariants(snapshot(batches=[BatchRow(1, 10, 4), BatchRow(2, 4, 4)]))
    assert check_invariants(snapshot(batches=[BatchRow(1, 2, 3), BatchRow(2, 4, 4)]))  # > received
    assert check_invariants(snapshot(on_hand=-1, batches=[], movements=[], reserved=0,
                                     active_reserved=0))  # fmt: skip


def test_drift_between_batches_is_caught_even_when_the_totals_still_match():
    # Totals agree (3 + 4 = 7) but batch 1 and batch 2 each disagree with their own movements.
    drifted = snapshot(batches=[BatchRow(1, 10, 2), BatchRow(2, 4, 5)])
    assert any("batch 1" in problem for problem in check_invariants(drifted))
    assert any("batch 2" in problem for problem in check_invariants(drifted))


def test_a_movement_for_a_batch_that_does_not_exist_is_caught():
    orphan = snapshot(movements=[*snapshot().movements, MovementRow(99, 5)])
    problems = check_invariants(orphan)
    assert any("unknown batch 99" in problem for problem in problems)


# --- a long random history never breaks the rules ----------------------------------


class Ledger:
    """A plain in-memory copy of the stock rules, driven by the same pure functions."""

    def __init__(self):
        self.batches = {}  # id -> [received, remaining]
        self.movements = []
        self.holds = {}  # id -> qty (active)
        self.next_batch = 1
        self.next_hold = 1

    @property
    def on_hand(self):
        return sum(r for _, r in self.batches.values())

    @property
    def reserved(self):
        return sum(self.holds.values())

    def receive(self, qty):
        self.batches[self.next_batch] = [qty, qty]
        self.movements.append(MovementRow(self.next_batch, qty))
        self.next_batch += 1

    def reserve(self, qty):
        if self.on_hand - self.reserved < qty:
            raise InsufficientStock(None, qty, self.on_hand - self.reserved)
        self.holds[self.next_hold] = qty
        self.next_hold += 1

    def release(self, hold_id):
        self.holds.pop(hold_id)

    def confirm(self, hold_id):
        qty = self.holds.pop(hold_id)
        ordered = [(bid, rem) for bid, (_, rem) in sorted(self.batches.items())]
        for batch_id, take in allocate_fifo(ordered, qty):
            self.batches[batch_id][1] -= take
            self.movements.append(MovementRow(batch_id, -take))

    def snapshot(self):
        return LedgerSnapshot(
            on_hand=self.on_hand,
            reserved=self.reserved,
            active_reserved=sum(self.holds.values()),
            batches=[BatchRow(i, r, rem) for i, (r, rem) in self.batches.items()],
            movements=list(self.movements),
        )


def test_random_histories_never_break_the_rules_or_oversell():
    for seed in range(200):
        rng = random.Random(seed)
        ledger = Ledger()
        for _ in range(60):
            action = rng.choice(["receive", "reserve", "reserve", "release", "confirm", "confirm"])
            if action == "receive":
                ledger.receive(rng.randint(1, 8))
            elif action == "reserve":
                try:
                    ledger.reserve(rng.randint(1, 6))
                except InsufficientStock as error:
                    assert error.available < error.requested
            elif ledger.holds:
                hold = rng.choice(sorted(ledger.holds))
                getattr(ledger, action)(hold)
            assert check_invariants(ledger.snapshot()) == [], (seed, action)
            assert 0 <= ledger.reserved <= ledger.on_hand
