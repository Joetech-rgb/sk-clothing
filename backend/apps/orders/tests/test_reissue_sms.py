"""A staff reissue of the delivery code sends the new code by SMS.

Like test_dispatch_sms.py, these replace the code service with stand-ins and check only the
wiring. The admin action itself is covered by test_dispatch.py (run_action reissue_code_action).
"""

from types import SimpleNamespace

import pytest

from apps.orders import services


@pytest.fixture
def wired(monkeypatch):
    order = SimpleNamespace(pk=7, contact_phone="+233201234567", reference="SK-ABCDEFGH")
    queued = []
    monkeypatch.setattr(
        services, "Order", SimpleNamespace(objects=SimpleNamespace(get=lambda pk: order))
    )
    monkeypatch.setattr(services.delivery_codes, "reissue_delivery_code", lambda *a, **kw: "222222")
    monkeypatch.setattr(services.delivery_codes, "issue_number_for", lambda order_id: 2)
    monkeypatch.setattr(
        services.notifications, "queue_delivery_code", lambda o, **kw: queued.append((o, kw))
    )
    return order, queued


@pytest.mark.django_db
def test_reissue_queues_the_new_code_as_the_next_issue(wired):
    order, queued = wired
    assert services.reissue_code(7, actor="user:1") == "222222"
    assert queued == [(order, {"code": "222222", "issue_number": 2})]


@pytest.mark.django_db
def test_a_code_that_cannot_be_reissued_queues_nothing(wired, monkeypatch):
    _, queued = wired

    def refuse(*args, **kwargs):
        raise services.delivery_codes.CodeAlreadyUsed

    monkeypatch.setattr(services.delivery_codes, "reissue_delivery_code", refuse)
    with pytest.raises(services.delivery_codes.CodeAlreadyUsed):
        services.reissue_code(7, actor="user:1")
    assert queued == []
