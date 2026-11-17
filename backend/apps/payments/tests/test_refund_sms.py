"""Refund messages: the wiring in payments/refunds.py.

The database parts are replaced with stand-ins, so these check only what _apply_answer and
_fail hand to the notifications. test_refunds.py covers the real refund flow.
"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from apps.payments import refunds
from apps.payments.models import Refund

NOW = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def wired(monkeypatch):
    order = SimpleNamespace(pk=7, contact_phone="+233201234567", reference="SK-ABCDEFGH")
    refund = SimpleNamespace(
        pk=5,
        order_id=7,
        amount_pesewas=12050,
        status=Refund.Status.SUBMITTED,
        paystack_refund_id="",
        checked_at=None,
        processed_at=None,
        attempts=1,
        last_error="",
        next_attempt_at=None,
        saved=0,
    )
    refund.save = lambda: setattr(refund, "saved", refund.saved + 1)
    sent = []
    refund_rows = SimpleNamespace(select_for_update=lambda: SimpleNamespace(get=lambda pk: refund))
    order_rows = SimpleNamespace(filter=lambda **kw: SimpleNamespace(first=lambda: order))
    monkeypatch.setattr(
        refunds, "Refund", SimpleNamespace(objects=refund_rows, Status=Refund.Status)
    )
    monkeypatch.setattr(refunds, "Order", SimpleNamespace(objects=order_rows))
    monkeypatch.setattr(refunds, "_order_event", lambda *a, **kw: None)
    monkeypatch.setattr(refunds, "_log", lambda *a, **kw: None)
    monkeypatch.setattr(
        refunds, "option", lambda name: {"max_attempts": 3, "backoff_minutes": [1, 5]}[name]
    )

    def record(kind):
        return lambda o, **kw: sent.append((kind, o, kw))

    monkeypatch.setattr(refunds.notifications, "queue_refund_started", record("started"))
    monkeypatch.setattr(refunds.notifications, "queue_refund_manual", record("manual"))
    return order, refund, sent


def answer(status):
    return SimpleNamespace(refund_id="r1", status=status)


@pytest.mark.django_db
@pytest.mark.parametrize("status", ["pending", "processing", "processed"])
def test_an_accepted_refund_tells_the_customer(wired, status):
    order, refund, sent = wired
    refunds._apply_answer(5, answer(status), NOW)
    assert sent == [("started", order, {"refund_id": 5, "amount_pesewas": 12050})]
    assert refund.saved == 1


@pytest.mark.django_db
@pytest.mark.parametrize("status", ["failed", "needs-attention"])
def test_a_refund_that_did_not_go_through_sends_no_started_message(wired, monkeypatch, status):
    _, _, sent = wired
    monkeypatch.setattr(refunds, "_fail", lambda *a, **kw: "requested")
    refunds._apply_answer(5, answer(status), NOW)
    assert sent == []


@pytest.mark.django_db
def test_a_refund_handed_to_a_person_tells_the_customer(wired):
    order, refund, sent = wired
    result = refunds._fail(5, "outcome_unknown", give_up=True, now=NOW)
    assert result == Refund.Status.MANUAL_RESOLUTION
    assert sent == [("manual", order, {"refund_id": 5})]


@pytest.mark.django_db
def test_a_refund_that_will_be_tried_again_sends_nothing(wired):
    _, refund, sent = wired
    result = refunds._fail(5, "paystack_failed_refund", give_up=False, now=NOW)
    assert result == Refund.Status.REQUESTED
    assert sent == []


@pytest.mark.django_db
def test_a_messaging_problem_never_blocks_the_refund(wired, monkeypatch):
    _, refund, _ = wired

    def broken(*args, **kwargs):
        raise RuntimeError("the outbox is down")

    monkeypatch.setattr(refunds.notifications, "queue_refund_started", broken)
    result = refunds._apply_answer(5, answer("processing"), NOW)
    assert result == Refund.Status.PROCESSING
    assert refund.saved == 1 and refund.paystack_refund_id == "r1"
