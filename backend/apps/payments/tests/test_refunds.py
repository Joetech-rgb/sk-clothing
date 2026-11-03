import logging
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.orders.models import OrderEvent
from apps.payments import refunds
from apps.payments.client import PaystackError
from apps.payments.models import ImmutableError, PaymentAttempt, Refund, RefundEvent
from apps.payments.tasks import check_overdue_refunds
from apps.payments.tasks import process_refunds as process_task
from apps.payments.tests.helpers import (
    EMAIL,
    fake,
    order_row,
    paid_order,
    place_order,
    refund_requested_order,
    start_ok,
    verify_page,
)

pytestmark = pytest.mark.django_db

T0 = timezone.now()


def run(minutes=0):
    return refunds.process_refunds(fake(), now=T0 + timedelta(minutes=minutes))


def the_refund(reference):
    return Refund.objects.get(payment__reference=reference)


def order_refund_status(order):
    return order_row(order["reference"]).refund


def order_refund_events(order):
    names = (
        "refund_submitted",
        "refund_processing",
        "refund_processed",
        "refund_failed",
        "refund_retry",
        "refund_escalated",
        "refund_resolved_manually",
    )
    return [
        e
        for e in OrderEvent.objects.filter(order__reference=order["reference"]).values_list(
            "event", flat=True
        )
        if e in names
    ]


# --- finding what to refund -------------------------------------------------------------------


def test_an_order_that_could_not_be_fulfilled_gets_one_refund_for_the_full_payment(shop):
    order, reference = refund_requested_order(shop)
    assert refunds.queue_refunds(now=T0) == 1
    refund = the_refund(reference)
    assert refund.status == "requested" and refund.reason == "order_refund"
    assert refund.amount_pesewas == order["total"]["pesewas"] and refund.currency == "GHS"
    assert refund.idempotency_key == f"refund:{reference}"
    assert [e.kind for e in refund.events.all()] == ["requested"]
    assert order_refund_status(order) == "requested"


def test_running_it_again_and_again_never_makes_a_second_refund(shop):
    _, reference = refund_requested_order(shop)
    assert [refunds.queue_refunds(now=T0) for _ in range(4)] == [1, 0, 0, 0]
    assert Refund.objects.count() == 1


def test_a_normal_paid_order_is_never_refunded(shop):
    paid_order(shop)
    assert refunds.queue_refunds(now=T0) == 0 and Refund.objects.count() == 0


def test_an_order_that_needs_a_refund_but_has_no_confirmed_payment_is_reported(shop, caplog):
    from apps.orders.models import Order
    from apps.orders.services import transition
    from apps.orders.states import Event

    caplog.set_level(logging.ERROR)
    order = place_order([(shop.shirt, 1)])
    row = order_row(order["reference"])
    transition(
        row.pk, Event.PAYMENT_CONFIRMED, actor="test"
    )  # marked paid with no Paystack payment
    transition(row.pk, Event.CANCEL, actor="test")
    assert Order.objects.get(pk=row.pk).refund == "requested"
    assert refunds.queue_refunds(now=T0) == 0
    assert any("has no confirmed payment" in r.getMessage() for r in caplog.records)


def test_a_payment_that_arrived_twice_gets_its_own_refund_and_the_order_is_untouched(shop):
    order = place_order([(shop.shirt, 2)])
    first, second = start_ok(order["reference"]), start_ok(order["reference"])
    assert verify_page(first).json()["outcome"] == "paid"
    assert verify_page(second).json()["outcome"] == "duplicate"
    assert refunds.queue_refunds(now=T0) == 1
    refund = Refund.objects.get()
    assert refund.payment.reference == second and refund.reason == "duplicate_payment"
    assert not Refund.objects.filter(payment__reference=first).exists()
    run()
    assert order_row(order["reference"]).refund == "none"  # the order has nothing to refund
    assert Refund.objects.get().status == "submitted"
    fake().set_refund_status(second, "processed")
    run(6)
    assert Refund.objects.get().status == "processed" and order_refund_status(order) == "none"


# --- the good path ----------------------------------------------------------------------------


def test_a_refund_is_sent_once_with_the_full_amount_and_followed_to_the_end(shop):
    order, reference = refund_requested_order(shop)
    summary = run()
    assert (summary.queued, summary.submitted) == (1, 1)
    assert fake().refund_calls == [
        {"transaction": reference, "amount": order["total"]["pesewas"], "currency": "GHS"}
    ]
    refund = the_refund(reference)
    assert refund.status == "submitted" and refund.paystack_refund_id == "rf_1"
    assert refund.attempts == 1 and refund.submitted_at is not None
    assert order_refund_status(order) == "submitted"
    fake().set_refund_status(reference, "processed")
    run(6)
    refund = the_refund(reference)
    assert refund.status == "processed" and refund.processed_at is not None
    assert order_refund_status(order) == "processed"
    assert [e.kind for e in refund.events.all()] == ["requested", "sending", "processed"]
    assert order_refund_events(order) == ["refund_submitted", "refund_processed"]
    assert len(fake().refund_calls) == 1  # never sent again


def test_a_refund_that_goes_through_processing_is_followed_step_by_step(shop):
    order, reference = refund_requested_order(shop)
    run()
    fake().set_refund_status(reference, "processing")
    run(6)
    assert (
        the_refund(reference).status == "processing" and order_refund_status(order) == "processing"
    )
    fake().set_refund_status(reference, "processed")
    run(12)
    assert the_refund(reference).status == "processed" and order_refund_status(order) == "processed"
    assert order_refund_events(order) == [
        "refund_submitted",
        "refund_processing",
        "refund_processed",
    ]


def test_paystack_is_not_asked_about_a_refund_too_often(shop):
    _, reference = refund_requested_order(shop)
    run()
    fetches = []
    original = fake().fetch_refund
    fake().fetch_refund = lambda refund_id: (fetches.append(refund_id), original(refund_id))[1]
    run(1)
    run(2)
    assert fetches == []
    run(6)
    assert len(fetches) == 1


def test_a_refund_still_pending_stays_submitted(shop):
    order, reference = refund_requested_order(shop)
    run()
    run(6)
    assert the_refund(reference).status == "submitted" and order_refund_status(order) == "submitted"


def test_an_order_that_asks_for_a_refund_after_a_cancel_of_a_paid_order_is_refunded_too(shop):
    from apps.orders.services import transition
    from apps.orders.states import Event

    order, reference = paid_order(shop)
    transition(order_row(order["reference"]).pk, Event.CANCEL, actor="staff")
    run()
    fake().set_refund_status(reference, "processed")
    run(6)
    assert order_refund_status(order) == "processed"
    assert the_refund(reference).amount_pesewas == order["total"]["pesewas"]


# --- when sending does not work ---------------------------------------------------------------


def test_trouble_reaching_paystack_means_a_pause_and_another_try(shop, caplog):
    caplog.set_level(logging.INFO)
    order, reference = refund_requested_order(shop)
    fake().fail_refund_create = PaystackError("ama@example.com is down", retryable=True)
    run()
    refund = the_refund(reference)
    assert (refund.status, refund.attempts, refund.last_error) == (
        "requested",
        1,
        "paystack_unreachable",
    )
    assert refund.next_attempt_at == T0 + timedelta(minutes=5)
    assert order_refund_status(order) == "requested"
    assert order_refund_events(order) == ["refund_submitted", "refund_failed", "refund_retry"]
    run(1)  # too early
    assert len(fake().refund_calls) == 1
    fake().fail_refund_create = None
    run(6)
    assert len(fake().refund_calls) == 2 and the_refund(reference).status == "submitted"
    assert "ama@example.com" not in refund.last_error
    assert "ama@example.com" not in "\n".join(r.getMessage() for r in caplog.records)


def test_after_the_last_failed_attempt_a_person_takes_over(shop, caplog):
    caplog.set_level(logging.ERROR)
    order, reference = refund_requested_order(shop)
    fake().fail_refund_create = PaystackError("down", retryable=True)
    run(0)
    assert the_refund(reference).next_attempt_at == T0 + timedelta(minutes=5)
    run(6)
    assert the_refund(reference).next_attempt_at == T0 + timedelta(minutes=36)  # a longer pause
    run(40)
    refund = the_refund(reference)
    assert (refund.status, refund.attempts) == ("manual_resolution", 3)
    assert refund.next_attempt_at is None
    assert order_refund_status(order) == "manual_resolution"
    assert any("needs a person" in r.getMessage() for r in caplog.records)
    calls = len(fake().refund_calls)
    run(500)
    assert len(fake().refund_calls) == calls  # nothing more happens by itself


def test_a_refusal_goes_straight_to_a_person(shop):
    order, reference = refund_requested_order(shop)
    fake().fail_refund_create = PaystackError("no", retryable=False)
    run()
    refund = the_refund(reference)
    assert (refund.status, refund.attempts, refund.last_error) == (
        "manual_resolution",
        1,
        "paystack_refused",
    )
    assert order_refund_status(order) == "manual_resolution"


def test_a_refund_paystack_reports_as_failed_is_tried_again_and_then_handed_over(shop):
    order, reference = refund_requested_order(shop)
    # (minute it is sent, minute Paystack's failure is noticed, status afterwards)
    rounds = [(0, 6, "requested"), (12, 18, "requested"), (50, 56, "manual_resolution")]
    for sent_at, noticed_at, expected in rounds:
        run(sent_at)
        assert the_refund(reference).status == "submitted"
        fake().set_refund_status(reference, "failed")
        run(noticed_at)
        assert the_refund(reference).status == expected
        fake().refunds.clear()  # Paystack credits the money back, so a new refund may be made
    refund = the_refund(reference)
    assert refund.attempts == 3 and refund.last_error == "paystack_failed_refund"
    assert len(fake().refund_calls) == 3 and order_refund_status(order) == "manual_resolution"
    assert order_refund_events(order).count("refund_retry") == 2


def test_paystack_needing_the_customers_bank_details_goes_to_a_person_at_once(shop):
    order, reference = refund_requested_order(shop)
    run()
    fake().set_refund_status(reference, "needs-attention")
    run(6)
    refund = the_refund(reference)
    assert (refund.status, refund.last_error) == ("manual_resolution", "needs_bank_details")
    assert order_refund_status(order) == "manual_resolution"


def test_a_failed_status_from_paystack_means_another_attempt_after_a_pause(shop):
    order, reference = refund_requested_order(shop)
    run()
    fake().set_refund_status(reference, "failed")
    run(6)
    refund = the_refund(reference)
    assert (refund.status, refund.last_error) == ("requested", "paystack_failed_refund")
    assert order_refund_status(order) == "requested" and refund.attempts == 1


def test_a_status_we_do_not_know_changes_nothing_and_is_noted(shop, caplog):
    caplog.set_level(logging.WARNING)
    order, reference = refund_requested_order(shop)
    run()
    fake().set_refund_status(reference, "something-new")
    run(6)
    assert the_refund(reference).status == "submitted"
    assert any("status we do not know" in r.getMessage() for r in caplog.records)


def test_when_paystack_cannot_be_asked_the_follow_up_is_just_tried_again_later(shop):
    _, reference = refund_requested_order(shop)
    run()
    fake().fail_refund_fetch = PaystackError("down", retryable=True)
    run(6)
    assert the_refund(reference).status == "submitted"
    fake().fail_refund_fetch = None
    fake().set_refund_status(reference, "processed")
    run(12)
    assert the_refund(reference).status == "processed"


# --- never refunding twice --------------------------------------------------------------------


def test_a_request_that_may_have_got_through_is_never_sent_blindly_a_third_time(shop):
    """The refund was created at Paystack but the answer was lost. Asking again is refused by
    Paystack (it would refund more than was paid), so a person checks. Money goes out once."""
    order, reference = refund_requested_order(shop)
    fake().create_then_fail = PaystackError("lost the answer", retryable=True)
    run(0)
    assert len(fake().refunds) == 1  # it did go through
    fake().create_then_fail = None
    run(6)
    refund = the_refund(reference)
    assert refund.status == "manual_resolution" and refund.last_error == "paystack_refused"
    assert len(fake().refunds) == 1 and len(fake().refund_calls) == 2
    assert order_refund_status(order) == "manual_resolution"


def test_a_refund_sent_but_never_answered_is_given_to_a_person_not_sent_again(shop):
    order, reference = refund_requested_order(shop)
    refunds.queue_refunds(now=T0)
    Refund.objects.update(status="submitted", attempts=1, submitted_at=T0)
    from apps.orders.services import transition
    from apps.orders.states import Event

    transition(order_row(order["reference"]).pk, Event.REFUND_SUBMITTED, actor="t")
    assert refunds.mark_stuck_refunds(now=T0 + timedelta(minutes=5)) == 0  # not stuck yet
    assert refunds.mark_stuck_refunds(now=T0 + timedelta(minutes=11)) == 1
    refund = the_refund(reference)
    assert (refund.status, refund.last_error) == ("manual_resolution", "outcome_unknown")
    assert fake().refund_calls == []


# --- people -----------------------------------------------------------------------------------


def make_manual(shop):
    order, reference = refund_requested_order(shop)
    fake().fail_refund_create = PaystackError("no", retryable=False)
    run()
    fake().fail_refund_create = None
    return order, reference


def test_staff_can_record_that_a_refund_was_made_outside_the_system(shop):
    order, reference = make_manual(shop)
    refund = the_refund(reference)
    refunds.resolve_outside_system(
        refund.pk, actor="user:7", note="  Refunded in the   Paystack dashboard "
    )
    refund = the_refund(reference)
    assert refund.status == "processed" and refund.processed_at is not None
    assert (refund.resolved_by, refund.resolution_note) == (
        "user:7",
        "Refunded in the Paystack dashboard",
    )
    assert order_refund_status(order) == "processed"
    last = refund.events.last()
    assert (last.kind, last.actor) == ("resolved_outside_system", "user:7")
    assert "dashboard" in last.detail


def test_only_a_refund_that_needs_a_person_can_be_resolved_that_way(shop):
    _, reference = refund_requested_order(shop)
    run()
    refund = the_refund(reference)
    with pytest.raises(refunds.NotAllowed):
        refunds.resolve_outside_system(refund.pk, actor="user:7", note="done")
    assert the_refund(reference).status == "submitted"


def test_resolving_needs_a_note_and_cannot_be_done_twice(shop):
    _, reference = make_manual(shop)
    refund = the_refund(reference)
    with pytest.raises(refunds.NotAllowed):
        refunds.resolve_outside_system(refund.pk, actor="user:7", note="   ")
    refunds.resolve_outside_system(refund.pk, actor="user:7", note="done")
    with pytest.raises(refunds.NotAllowed):
        refunds.resolve_outside_system(refund.pk, actor="user:8", note="again")
    assert the_refund(reference).resolved_by == "user:7"


def test_a_refund_unresolved_for_a_day_raises_an_alarm(shop, caplog):
    caplog.set_level(logging.ERROR)
    _, reference = refund_requested_order(shop)
    refunds.queue_refunds(now=T0)
    refund = the_refund(reference)
    assert refunds.check_overdue_refunds(now=timezone.now()) == 0
    Refund.objects.filter(pk=refund.pk).update(created_at=timezone.now() - timedelta(hours=25))
    assert refunds.check_overdue_refunds(now=timezone.now()) == 1
    message = next(
        r.getMessage() for r in caplog.records if "unresolved after 24 hours" in r.getMessage()
    )
    assert str(refund.pk) in message and EMAIL not in message
    Refund.objects.filter(pk=refund.pk).update(status="processed")
    assert refunds.check_overdue_refunds(now=timezone.now()) == 0


def test_the_limits_can_be_changed_in_settings(shop, settings):
    settings.REFUND_LIMITS = {"max_attempts": 1}
    _, reference = refund_requested_order(shop)
    fake().fail_refund_create = PaystackError("down", retryable=True)
    run()
    assert the_refund(reference).status == "manual_resolution"


# --- the scheduled tasks ----------------------------------------------------------------------


def test_the_scheduled_task_does_a_full_round(shop):
    _, reference = refund_requested_order(shop)
    result = process_task()
    assert result == {"queued": 1, "submitted": 1, "synced": 0, "stuck": 0}
    assert the_refund(reference).status == "submitted"


def test_without_a_paystack_key_the_task_says_so_and_does_nothing(shop, settings, caplog):
    caplog.set_level(logging.ERROR)
    refund_requested_order(shop)
    settings.PAYSTACK_CLIENT = ""
    settings.PAYSTACK_SECRET_KEY = ""
    assert process_task() == {"queued": 0, "submitted": 0, "synced": 0, "stuck": 0}
    assert Refund.objects.count() == 0
    assert any("Paystack is not configured" in r.getMessage() for r in caplog.records)


def test_the_overdue_task_reports_how_many(shop):
    refund_requested_order(shop)
    refunds.queue_refunds(now=T0)
    Refund.objects.update(created_at=timezone.now() - timedelta(hours=30))
    assert check_overdue_refunds() == 1


# --- end to end, privacy, history -------------------------------------------------------------


def test_a_late_payer_who_finds_no_stock_ends_up_refunded_and_can_see_it(shop):
    from rest_framework.test import APIClient

    order, reference = refund_requested_order(shop)
    run()
    fake().set_refund_status(reference, "processed")
    run(6)
    response = APIClient().post(
        "/api/v1/orders/lookup/",
        {"reference": order["reference"], "phone": "0241230001"},
        format="json",
    )
    data = response.json()
    assert (data["payment_status"], data["fulfilment_status"], data["refund_status"]) == (
        "paid",
        "not_fulfillable",
        "processed",
    )


def test_nothing_personal_reaches_the_logs_or_the_stored_error(shop, caplog):
    caplog.set_level(logging.DEBUG)
    order, reference = refund_requested_order(shop)
    fake().fail_refund_create = PaystackError(
        "ama@example.com 0241230001 card 4084", retryable=True
    )
    run()
    text = "\n".join(f"{r.getMessage()} {r.args}" for r in caplog.records)
    stored = the_refund(reference)
    blob = text + stored.last_error + "".join(e.detail for e in stored.events.all())
    for secret in ("ama@example.com", "0241230001", "4084", "Ama Mensah"):
        assert secret not in blob


def test_refund_history_cannot_be_rewritten(shop):
    refund_requested_order(shop)
    refunds.queue_refunds(now=T0)
    event = RefundEvent.objects.first()
    event.kind = "tampered"
    with pytest.raises(ImmutableError):
        event.save()
    with pytest.raises(ImmutableError):
        event.delete()
    with pytest.raises(ImmutableError):
        RefundEvent.objects.all().update(actor="x")
    with pytest.raises(ImmutableError):
        RefundEvent.objects.all().delete()


def test_a_payment_can_have_only_one_refund_in_the_database(shop):
    from django.db import IntegrityError, transaction

    _, reference = refund_requested_order(shop)
    refunds.queue_refunds(now=T0)
    attempt = PaymentAttempt.objects.get(reference=reference)
    with pytest.raises(IntegrityError), transaction.atomic():
        Refund.objects.create(
            payment=attempt,
            order_id=attempt.order_id,
            reason="order_refund",
            amount_pesewas=1,
            idempotency_key="refund:other",
        )


def test_a_full_round_also_hands_over_refunds_that_were_sent_and_never_answered(shop):
    refund_requested_order(shop)
    refunds.queue_refunds(now=T0)
    Refund.objects.update(status="submitted", attempts=1, submitted_at=T0)
    assert run(11).stuck == 1
    assert Refund.objects.get().status == "manual_resolution"


def test_the_refund_goes_to_the_payment_that_succeeded_not_an_earlier_failed_one(shop):
    from apps.orders.services import transition
    from apps.orders.states import Event

    order = place_order([(shop.shirt, 2)])
    failed = start_ok(order["reference"])
    fake().set_outcome(failed, status="failed")
    assert verify_page(failed).json()["payment_status"] == "failed"
    good = start_ok(order["reference"])
    assert verify_page(good).json()["outcome"] == "paid"
    transition(order_row(order["reference"]).pk, Event.CANCEL, actor="staff")
    run()
    assert [c["transaction"] for c in fake().refund_calls] == [good]
    assert Refund.objects.get().payment.reference == good


def test_a_refund_cannot_be_sent_before_its_retry_time_even_when_asked_directly(shop):
    _, reference = refund_requested_order(shop)
    fake().fail_refund_create = PaystackError("down", retryable=True)
    run(0)
    fake().fail_refund_create = None
    refund = the_refund(reference)
    assert (
        refunds.submit_refund(refund.pk, fake(), now=T0 + timedelta(minutes=1)) == refunds.SKIPPED
    )
    assert len(fake().refund_calls) == 1
    assert (
        refunds.submit_refund(refund.pk, fake(), now=T0 + timedelta(minutes=6)) != refunds.SKIPPED
    )
    assert len(fake().refund_calls) == 2
