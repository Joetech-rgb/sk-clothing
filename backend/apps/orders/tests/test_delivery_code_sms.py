"""The delivery code SMS: one plain-GSM part, one message per issue of the code."""

import string
from types import SimpleNamespace

import pytest

from apps.orders import notifications as n

ALLOWED = set(string.ascii_letters + string.digits + " .,:;!?()-/'\"%+=@&*#_")


@pytest.fixture
def sent(monkeypatch):
    calls = []
    monkeypatch.setattr(n.messaging, "queue_sms", lambda **kw: calls.append(kw))
    return calls


def an_order(phone="+233201234567"):
    return SimpleNamespace(pk=7, contact_phone=phone, reference="SK-ABCDEFGH")


def test_wording_is_plain_gsm_and_one_part_with_a_long_code():
    text = n.DELIVERY_CODE_SMS.format(reference="SK-ABCDEFGH", code="ABCD1234EFGH")
    assert not (set(text) - ALLOWED)
    assert len(text) <= 160
    assert text.startswith("S.K Clothing: ")


def test_the_message_carries_the_code_and_the_warning(sent):
    n.queue_delivery_code(an_order(), code="483920", issue_number=1)
    assert len(sent) == 1
    assert "483920" in sent[0]["text"]
    assert "only when you have your items" in sent[0]["text"]
    assert sent[0]["to_e164"] == "+233201234567"
    assert sent[0]["template"] == "delivery_code"


def test_a_reissued_code_gets_its_own_message_key(sent):
    n.queue_delivery_code(an_order(), code="111111", issue_number=1)
    n.queue_delivery_code(an_order(), code="222222", issue_number=2)
    keys = [c["idempotency_key"] for c in sent]
    assert keys == ["delivery_code-7-1", "delivery_code-7-2"]
    assert len(set(keys)) == 2


def test_the_same_issue_always_uses_the_same_key(sent):
    n.queue_delivery_code(an_order(), code="111111", issue_number=1)
    n.queue_delivery_code(an_order(), code="111111", issue_number=1)
    assert sent[0]["idempotency_key"] == sent[1]["idempotency_key"]


def test_no_phone_number_queues_nothing(sent):
    n.queue_delivery_code(an_order(phone=""), code="483920", issue_number=1)
    assert sent == []
