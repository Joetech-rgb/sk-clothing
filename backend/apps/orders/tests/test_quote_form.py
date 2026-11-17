"""The delivery fee form and the "ready to pay" message wording."""

import string

import pytest

from apps.orders import notifications as n
from apps.orders.admin import QuoteForm

ALLOWED = set(string.ascii_letters + string.digits + " .,:;!?()-/'\"%+=@&*#_")


@pytest.mark.parametrize(
    ("typed", "pesewas"),
    [("0", 0), ("30", 3000), ("30.00", 3000), ("45.50", 4550), ("5000", 500000)],
)
def test_the_fee_is_turned_into_whole_pesewas(typed, pesewas):
    form = QuoteForm({"fee": typed})
    assert form.is_valid()
    assert form.fee_pesewas() == pesewas


@pytest.mark.parametrize("typed", ["", "abc", "-1", "30.505", "5000.01"])
def test_a_bad_fee_is_refused(typed):
    assert not QuoteForm({"fee": typed}).is_valid()


def _text(where):
    values = {"reference": "SK-ABCDEFGH", "total": "99999.99", "fee": "5000.00"}
    return n.QUOTE_READY_SMS.format(where=where, **values)


def test_the_message_is_plain_gsm_in_both_forms():
    for where in (n.QUOTE_WHERE_PLAIN, n.QUOTE_WHERE_URL.format(url="https://shop.example.com.gh")):
        text = _text(where)
        assert not (set(text) - ALLOWED)
        assert text.startswith("S.K Clothing: ")
        assert "SK-ABCDEFGH" in text


def test_the_plain_message_fits_one_sms_part_with_worst_case_amounts():
    assert len(_text(n.QUOTE_WHERE_PLAIN)) <= n.ONE_SMS_PART


def test_a_link_that_makes_the_message_too_long_is_dropped(settings, monkeypatch):
    from types import SimpleNamespace

    queued = []
    monkeypatch.setattr(n.messaging, "queue_sms", lambda **kw: queued.append(kw))
    order = SimpleNamespace(
        pk=1,
        contact_phone="+233201234567",
        reference="SK-ABCDEFGH",
        total_pesewas=9999999,
        delivery_fee_pesewas=500000,
    )
    settings.STOREFRONT_URL = "https://a-very-long-shop-name-for-the-test.example.com.gh/"
    n.queue_quote_ready(order)
    assert len(queued) == 1
    assert len(queued[0]["text"]) <= n.ONE_SMS_PART
    assert queued[0]["text"].endswith(n.QUOTE_WHERE_PLAIN)


def test_a_short_link_is_kept(settings, monkeypatch):
    from types import SimpleNamespace

    queued = []
    monkeypatch.setattr(n.messaging, "queue_sms", lambda **kw: queued.append(kw))
    order = SimpleNamespace(
        pk=1,
        contact_phone="+233201234567",
        reference="SK-ABCDEFGH",
        total_pesewas=7500,
        delivery_fee_pesewas=2500,
    )
    settings.STOREFRONT_URL = "https://shop.example.com.gh/"
    n.queue_quote_ready(order)
    assert queued[0]["text"].endswith("Pay at https://shop.example.com.gh/orders")
    assert queued[0]["idempotency_key"] == "quote_ready-1"
