import random
from datetime import datetime, timedelta, timezone

import pytest

from apps.orders.pickup import is_uncollected, reminder_due, reminder_due_at, uncollected_after
from apps.orders.states import (
    FULFILMENT_TERMINAL,
    Event,
    Fulfilment,
    InvalidTransition,
    OrderState,
    Payment,
    Refund,
    apply_event,
    check_invariants,
    initial_state,
)

ALL_EVENTS = list(Event)


def play(state, *events):
    for event in events:
        state = apply_event(state, event).after
    return state


def reachable_states():
    """Every state any order can reach, by trying every event from every state found so far."""
    starts = [
        initial_state(),
        initial_state(cod=True),
        initial_state(awaiting_quote=True),
        initial_state(pickup=True),
    ]
    seen = set(starts)
    queue = list(starts)
    while queue:
        state = queue.pop()
        for event in ALL_EVENTS:
            try:
                after = apply_event(state, event).after
            except InvalidTransition:
                continue
            if after not in seen:
                seen.add(after)
                queue.append(after)
    return seen


# --- happy paths -----------------------------------------------------------------


def test_online_delivery_order_from_placed_to_delivered():
    s = initial_state()
    assert (s.payment, s.fulfilment) == (Payment.PENDING, Fulfilment.PENDING)
    s = play(s, Event.PAYMENT_CONFIRMED)
    assert (s.payment, s.fulfilment) == (Payment.PAID, Fulfilment.TO_PACK)
    s = play(s, Event.PACKED, Event.DISPATCHED, Event.DELIVERED)
    assert (s.payment, s.fulfilment, s.refund) == (Payment.PAID, Fulfilment.DELIVERED, Refund.NONE)


def test_pickup_order_is_collected():
    s = play(
        initial_state(pickup=True), Event.PAYMENT_CONFIRMED, Event.PACKED, Event.READY_FOR_PICKUP
    )
    assert apply_event(s, Event.COLLECTED).after.fulfilment == Fulfilment.COLLECTED


def test_pay_on_delivery_is_phoned_then_packed_then_paid_at_the_door():
    s = initial_state(cod=True)
    assert s.payment == Payment.COD_PENDING
    s = play(s, Event.COD_CONFIRMED)
    assert (s.payment, s.fulfilment) == (Payment.COD_CONFIRMED, Fulfilment.TO_PACK)
    s = play(s, Event.PACKED, Event.DISPATCHED, Event.DELIVERED)
    assert (s.payment, s.fulfilment) == (Payment.PAID, Fulfilment.DELIVERED)


def test_awaiting_quote_must_be_quoted_before_it_can_be_paid():
    s = initial_state(awaiting_quote=True)
    with pytest.raises(InvalidTransition):
        apply_event(s, Event.PAYMENT_CONFIRMED)
    s = play(s, Event.QUOTE_SET, Event.PAYMENT_CONFIRMED)
    assert s.fulfilment == Fulfilment.TO_PACK


def test_uncollected_order_can_then_be_refunded_by_cancelling():
    s = play(
        initial_state(pickup=True),
        Event.PAYMENT_CONFIRMED,
        Event.PACKED,
        Event.READY_FOR_PICKUP,
        Event.FLAG_UNCOLLECTED,
    )
    assert s.fulfilment == Fulfilment.UNCOLLECTED and s.refund == Refund.NONE
    s = apply_event(s, Event.CANCEL).after
    assert (s.fulfilment, s.refund) == (Fulfilment.CANCELLED, Refund.REQUESTED)


# --- late payment and refunds (ADR 0008) -----------------------------------------


def test_paid_but_no_stock_is_not_fulfillable_and_a_refund_starts():
    s = play(initial_state(), Event.PAYMENT_CONFIRMED, Event.STOCK_UNAVAILABLE)
    assert (s.payment, s.fulfilment, s.refund) == (
        Payment.PAID,
        Fulfilment.NOT_FULFILLABLE,
        Refund.REQUESTED,
    )


def test_money_arriving_for_an_already_cancelled_order_starts_a_refund():
    s = play(initial_state(), Event.CANCEL)
    assert s.payment == Payment.VOID
    s = apply_event(s, Event.PAYMENT_CONFIRMED).after
    assert (s.payment, s.fulfilment, s.refund) == (
        Payment.PAID,
        Fulfilment.CANCELLED,
        Refund.REQUESTED,
    )


def test_cancelling_a_paid_order_starts_a_refund_and_an_unpaid_one_does_not():
    paid = play(initial_state(), Event.PAYMENT_CONFIRMED, Event.CANCEL)
    assert (paid.fulfilment, paid.refund) == (Fulfilment.CANCELLED, Refund.REQUESTED)
    unpaid = play(initial_state(), Event.CANCEL)
    assert (unpaid.payment, unpaid.refund) == (Payment.VOID, Refund.NONE)


def test_a_failed_payment_can_be_retried_successfully():
    s = play(initial_state(), Event.PAYMENT_FAILED)
    assert s.payment == Payment.FAILED
    assert play(s, Event.PAYMENT_CONFIRMED).payment == Payment.PAID


def test_refund_goes_through_its_steps_and_failures_can_retry_or_escalate():
    base = play(initial_state(), Event.PAYMENT_CONFIRMED, Event.CANCEL)
    done = play(base, Event.REFUND_SUBMITTED, Event.REFUND_PROCESSING, Event.REFUND_PROCESSED)
    assert done.refund == Refund.PROCESSED
    failed = play(base, Event.REFUND_SUBMITTED, Event.REFUND_FAILED)
    assert play(failed, Event.REFUND_RETRY).refund == Refund.REQUESTED
    stuck = play(failed, Event.REFUND_ESCALATED)
    assert stuck.refund == Refund.MANUAL_RESOLUTION
    assert play(stuck, Event.REFUND_RESOLVED_MANUALLY).refund == Refund.PROCESSED


# --- replays are harmless ----------------------------------------------------------


def test_repeating_an_event_changes_nothing():
    s = initial_state()
    once = apply_event(s, Event.PAYMENT_CONFIRMED)
    again = apply_event(once.after, Event.PAYMENT_CONFIRMED)
    assert once.changed and not again.changed and again.after == once.after
    s = play(initial_state(), Event.PAYMENT_CONFIRMED, Event.CANCEL)
    assert not apply_event(s, Event.CANCEL).changed
    assert not apply_event(s, Event.PAYMENT_CONFIRMED).changed


def test_a_webhook_replayed_three_times_is_one_payment():
    s = initial_state()
    for _ in range(3):
        s = apply_event(s, Event.PAYMENT_CONFIRMED).after
    assert (s.payment, s.fulfilment, s.refund) == (Payment.PAID, Fulfilment.TO_PACK, Refund.NONE)


# --- things that must not be possible ------------------------------------------------


def test_events_that_skip_a_step_are_refused():
    s = initial_state()
    for event in (Event.PACKED, Event.DISPATCHED, Event.DELIVERED, Event.COLLECTED):
        with pytest.raises(InvalidTransition):
            apply_event(s, event)
    paid = play(s, Event.PAYMENT_CONFIRMED)
    for event in (Event.DISPATCHED, Event.DELIVERED, Event.READY_FOR_PICKUP):
        with pytest.raises(InvalidTransition):
            apply_event(paid, event)


def test_a_cod_order_cannot_be_marked_paid_online():
    with pytest.raises(InvalidTransition):
        apply_event(initial_state(cod=True), Event.PAYMENT_CONFIRMED)


def test_pay_on_delivery_needs_a_known_fee():
    with pytest.raises(ValueError):
        initial_state(cod=True, awaiting_quote=True)


def test_an_order_out_for_delivery_cannot_be_cancelled():
    s = play(initial_state(), Event.PAYMENT_CONFIRMED, Event.PACKED, Event.DISPATCHED)
    with pytest.raises(InvalidTransition):
        apply_event(s, Event.CANCEL)


def test_finished_orders_cannot_move_again():
    delivered = play(
        initial_state(), Event.PAYMENT_CONFIRMED, Event.PACKED, Event.DISPATCHED, Event.DELIVERED
    )
    for event in (Event.CANCEL, Event.PACKED, Event.DISPATCHED, Event.STOCK_UNAVAILABLE):
        with pytest.raises(InvalidTransition):
            apply_event(delivered, event)


def test_refunds_cannot_skip_steps_or_start_from_nothing():
    s = play(initial_state(), Event.PAYMENT_CONFIRMED)
    for event in (Event.REFUND_SUBMITTED, Event.REFUND_PROCESSED, Event.REFUND_RETRY):
        with pytest.raises(InvalidTransition):
            apply_event(s, event)


# --- every reachable state, checked exhaustively ---------------------------------------


def test_every_reachable_state_obeys_the_rules():
    states = reachable_states()
    assert {s.fulfilment for s in states} == set(Fulfilment)  # every status can be reached
    assert {s.payment for s in states} == set(Payment)
    assert {s.refund for s in states} == set(Refund)
    for state in states:
        assert check_invariants(state) == [], state


def test_every_event_can_happen_somewhere():
    used = set()
    for state in reachable_states():
        for event in ALL_EVENTS:
            try:
                if apply_event(state, event).changed:
                    used.add(event)
            except InvalidTransition:
                pass
    assert used == set(ALL_EVENTS)


def test_the_delivery_method_never_changes_and_is_respected():
    for state in reachable_states():
        for event in ALL_EVENTS:
            try:
                after = apply_event(state, event).after
            except InvalidTransition:
                continue
            assert after.pickup == state.pickup
    delivery = play(initial_state(), Event.PAYMENT_CONFIRMED, Event.PACKED)
    pickup = play(initial_state(pickup=True), Event.PAYMENT_CONFIRMED, Event.PACKED)
    for event in (Event.READY_FOR_PICKUP, Event.COLLECTED, Event.FLAG_UNCOLLECTED):
        with pytest.raises(InvalidTransition):
            apply_event(delivery, event)
    for event in (Event.DISPATCHED, Event.DELIVERED):
        with pytest.raises(InvalidTransition):
            apply_event(pickup, event)


def test_a_payment_cannot_fail_before_the_delivery_fee_is_set():
    with pytest.raises(InvalidTransition):
        apply_event(initial_state(awaiting_quote=True), Event.PAYMENT_FAILED)


def test_pickup_cannot_be_pay_on_delivery_or_awaiting_a_quote():
    with pytest.raises(ValueError):
        initial_state(pickup=True, cod=True)
    with pytest.raises(ValueError):
        initial_state(pickup=True, awaiting_quote=True)


def test_forbidden_combinations_are_unreachable():
    for state in reachable_states():
        if state.fulfilment in (Fulfilment.DELIVERED, Fulfilment.COLLECTED):
            assert state.payment == Payment.PAID
        if state.refund != Refund.NONE:
            assert state.payment == Payment.PAID
        if state.fulfilment == Fulfilment.TO_PACK:
            assert state.payment in (Payment.PAID, Payment.COD_CONFIRMED)


def test_money_taken_is_never_forgotten_and_refunds_never_vanish():
    for state in reachable_states():
        for event in ALL_EVENTS:
            try:
                after = apply_event(state, event).after
            except InvalidTransition:
                continue
            if state.payment == Payment.PAID:
                assert after.payment == Payment.PAID  # paid stays paid
            if state.refund != Refund.NONE:
                assert after.refund != Refund.NONE  # a refund never goes back to none
            if state.fulfilment in FULFILMENT_TERMINAL:
                assert after.fulfilment == state.fulfilment  # finished stays finished


def test_refunds_only_ever_follow_the_intended_path_and_processed_is_final():
    allowed = {
        (Refund.NONE, Refund.REQUESTED),
        (Refund.REQUESTED, Refund.SUBMITTED),
        (Refund.SUBMITTED, Refund.PROCESSING),
        (Refund.SUBMITTED, Refund.PROCESSED),
        (Refund.SUBMITTED, Refund.FAILED),
        (Refund.PROCESSING, Refund.PROCESSED),
        (Refund.PROCESSING, Refund.FAILED),
        (Refund.FAILED, Refund.REQUESTED),  # retry
        (Refund.FAILED, Refund.MANUAL_RESOLUTION),
        (Refund.MANUAL_RESOLUTION, Refund.PROCESSED),
    }
    for state in reachable_states():
        for event in ALL_EVENTS:
            try:
                after = apply_event(state, event).after
            except InvalidTransition:
                continue
            if after.refund != state.refund:
                assert (state.refund, after.refund) in allowed, (state, event)
            if state.refund == Refund.PROCESSED:
                assert after.refund == Refund.PROCESSED  # a customer is never refunded twice


def test_a_paid_dead_order_always_has_a_refund_path():
    for state in reachable_states():
        if state.payment == Payment.PAID and state.fulfilment in (
            Fulfilment.CANCELLED,
            Fulfilment.NOT_FULFILLABLE,
        ):
            assert state.refund != Refund.NONE


def test_random_event_storms_never_break_the_rules():
    rng = random.Random(7)
    for _ in range(3000):
        state = rng.choice(
            [
                initial_state(),
                initial_state(cod=True),
                initial_state(awaiting_quote=True),
                initial_state(pickup=True),
            ]
        )
        for _ in range(25):
            event = rng.choice(ALL_EVENTS)
            try:
                state = apply_event(state, event).after
            except InvalidTransition:
                continue
            assert check_invariants(state) == []


def test_invariant_checker_catches_each_kind_of_corruption():
    bad = [
        OrderState(Payment.PENDING, Fulfilment.PACKED),
        OrderState(Payment.COD_CONFIRMED, Fulfilment.DELIVERED),
        OrderState(Payment.PAID, Fulfilment.CANCELLED, Refund.NONE),
        OrderState(Payment.PENDING, Fulfilment.PENDING, Refund.REQUESTED),
        OrderState(Payment.PAID, Fulfilment.AWAITING_QUOTE),
        OrderState(Payment.FAILED, Fulfilment.AWAITING_QUOTE),
        OrderState(Payment.PAID, Fulfilment.OUT_FOR_DELIVERY, pickup=True),
        OrderState(Payment.PAID, Fulfilment.COLLECTED, pickup=False),
        OrderState(Payment.COD_PENDING, Fulfilment.PENDING, pickup=True),
    ]
    for state in bad:
        assert check_invariants(state), state


# --- pickup timing ---------------------------------------------------------------------

READY = datetime(2026, 11, 20, 9, 0, tzinfo=timezone.utc)


def test_pickup_reminder_is_day_three_and_hold_ends_day_seven():
    assert reminder_due_at(READY) == READY + timedelta(days=3)
    assert uncollected_after(READY) == READY + timedelta(days=7)


def test_pickup_reminder_window():
    assert not reminder_due(READY, READY + timedelta(days=3) - timedelta(seconds=1))
    assert reminder_due(READY, READY + timedelta(days=3))
    assert reminder_due(READY, READY + timedelta(days=7) - timedelta(seconds=1))
    assert not reminder_due(READY, READY + timedelta(days=7))


def test_uncollected_after_seven_days():
    assert not is_uncollected(READY, READY + timedelta(days=7) - timedelta(seconds=1))
    assert is_uncollected(READY, READY + timedelta(days=7))


def test_pickup_times_need_a_time_zone():
    naive = datetime(2026, 11, 20, 9, 0)
    with pytest.raises(ValueError):
        reminder_due_at(naive)
    with pytest.raises(ValueError):
        is_uncollected(READY, naive)
