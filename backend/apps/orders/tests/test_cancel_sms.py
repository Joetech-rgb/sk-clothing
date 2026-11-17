"""Cancelling a stale unpaid order texts the customer.

Like the other wiring tests, these replace the database parts with stand-ins and check only
what cancel_if_stale hands to the notification. The real cancel path is covered by
test_expiry.py.
"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from apps.orders import expiry

NOW = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)


class FakeQuery:
    def __init__(self, order):
        self.order = order

    def select_for_update(self):
        return self

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self.order


@pytest.fixture
def wired(monkeypatch):
    order = SimpleNamespace(
        pk=7,
        contact_phone="+233201234567",
        reference="SK-ABCDEFGH",
        reservations=SimpleNamespace(all=lambda: []),
    )
    queued = []
    monkeypatch.setattr(expiry, "Order", SimpleNamespace(objects=FakeQuery(order)))
    monkeypatch.setattr(expiry, "transition", lambda *a, **kw: None)
    monkeypatch.setattr(expiry.inventory, "release", lambda ids: None)
    monkeypatch.setattr(expiry.notifications, "queue_cancelled_unpaid", queued.append)
    return order, queued


@pytest.mark.django_db
def test_a_stale_order_is_cancelled_and_the_customer_is_told(wired):
    order, queued = wired
    assert expiry.cancel_if_stale(7, NOW) is True
    assert queued == [order]


@pytest.mark.django_db
def test_an_order_that_is_not_stale_sends_nothing(wired, monkeypatch):
    _, queued = wired
    monkeypatch.setattr(expiry, "Order", SimpleNamespace(objects=FakeQuery(None)))
    assert expiry.cancel_if_stale(7, NOW) is False
    assert queued == []


@pytest.mark.django_db
def test_a_cancel_that_fails_sends_nothing(wired, monkeypatch):
    _, queued = wired

    def refuse(*args, **kwargs):
        raise RuntimeError("could not cancel")

    monkeypatch.setattr(expiry, "transition", refuse)
    with pytest.raises(RuntimeError):
        expiry.cancel_if_stale(7, NOW)
    assert queued == []
