"""Dispatching an order sends the delivery code by SMS.

These tests replace the state machine and the code service with stand-ins, so they check only
the wiring: what dispatch hands to the notification, and that a failure sends nothing. The
real dispatch path is covered by test_dispatch.py, which now also runs through the outbox.
"""

from types import SimpleNamespace

import pytest

from apps.orders import services


@pytest.fixture
def wired(monkeypatch):
    order = SimpleNamespace(pk=7, contact_phone="+233201234567", reference="SK-ABCDEFGH")
    queued = []
    monkeypatch.setattr(services, "transition", lambda *a, **kw: None)
    monkeypatch.setattr(
        services, "Order", SimpleNamespace(objects=SimpleNamespace(get=lambda pk: order))
    )
    monkeypatch.setattr(services.delivery_codes, "issue_delivery_code", lambda *a, **kw: "483920")
    monkeypatch.setattr(services.delivery_codes, "issue_number_for", lambda order_id: 1)
    monkeypatch.setattr(
        services.notifications, "queue_delivery_code", lambda o, **kw: queued.append((o, kw))
    )
    return order, queued


@pytest.mark.django_db
def test_dispatch_queues_the_code_and_returns_it(wired):
    order, queued = wired
    assert services.dispatch_order(7, actor="user:1") == "483920"
    assert queued == [(order, {"code": "483920", "issue_number": 1})]


@pytest.mark.django_db
def test_a_failed_dispatch_queues_nothing(wired, monkeypatch):
    _, queued = wired

    def refuse(*args, **kwargs):
        raise RuntimeError("not packed")

    monkeypatch.setattr(services, "transition", refuse)
    with pytest.raises(RuntimeError):
        services.dispatch_order(7, actor="user:1")
    assert queued == []
