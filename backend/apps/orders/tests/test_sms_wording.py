"""Every customer SMS must stay one plain-GSM part.

One curly quote or emoji switches an SMS to Unicode, which cuts the limit from 160 to
70 characters per part and makes it cost more. Worst-case values are used on purpose.
"""

import string

import pytest

from apps.orders import notifications as n

ALLOWED = set(string.ascii_letters + string.digits + " .,:;!?()-/'\"%+=@&*#_")
WORST_CASE = {"reference": "SK-ABCDEFGH", "total": "99999.99", "amount": "99999.99"}

WORDINGS = {
    "payment_received": n.PAYMENT_RECEIVED_SMS,
    "order_received_cod": n.ORDER_RECEIVED_COD_SMS,
    "awaiting_quote": n.AWAITING_QUOTE_SMS,
    "cancelled_unpaid": n.CANCELLED_UNPAID_SMS,
    "refund_started": n.REFUND_STARTED_SMS,
    "refund_manual": n.REFUND_MANUAL_SMS,
}


@pytest.mark.parametrize("name", WORDINGS)
def test_plain_gsm_characters_only(name):
    text = WORDINGS[name].format(**WORST_CASE)
    bad = sorted(set(text) - ALLOWED)
    assert not bad, f"{name} uses characters that force Unicode SMS: {bad}"


@pytest.mark.parametrize("name", WORDINGS)
def test_fits_one_sms_part(name):
    text = WORDINGS[name].format(**WORST_CASE)
    assert len(text) <= 160, f"{name} is {len(text)} characters"


@pytest.mark.parametrize("name", WORDINGS)
def test_carries_the_reference_and_shop_name(name):
    text = WORDINGS[name].format(**WORST_CASE)
    assert "SK-ABCDEFGH" in text
    assert text.startswith("S.K Clothing: ")


def test_ghs_has_no_float_rounding():
    assert n._ghs(7500) == "75.00"
    assert n._ghs(7505) == "75.05"
    assert n._ghs(5) == "0.05"
