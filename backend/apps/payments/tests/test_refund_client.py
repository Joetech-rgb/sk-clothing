"""The real client's refund calls, against a small fake of Paystack's server."""

import pytest

from apps.payments.client import PaystackError
from apps.payments.tests.test_client import ok, paystack  # noqa: F401 (shared fixture)


def test_a_refund_is_created_with_the_full_amount_stated(paystack):  # noqa: F811
    paystack.next_response = ok(
        {"id": 9001, "status": "pending", "amount": 12550, "currency": "GHS"}
    )
    answer = paystack.client.create_refund(
        transaction_reference="SK123-aa",
        amount_pesewas=12550,
        currency="GHS",
        merchant_note="Refund order_refund for order 7",
    )
    assert (answer.refund_id, answer.status, answer.amount) == ("9001", "pending", 12550)
    (request,) = paystack.requests
    assert request["method"] == "POST" and request["path"] == "/refund"
    assert request["body"] == {
        "transaction": "SK123-aa",
        "amount": 12550,
        "currency": "GHS",
        "merchant_note": "Refund order_refund for order 7",
    }
    assert isinstance(request["body"]["amount"], int)
    assert request["auth"].startswith("Bearer ")


def test_a_refund_is_fetched_by_its_own_id(paystack):  # noqa: F811
    paystack.next_response = ok({"id": 9001, "status": "processed", "amount": 12550})
    answer = paystack.client.fetch_refund("9001")
    assert (answer.refund_id, answer.status) == ("9001", "processed")
    assert (
        paystack.requests[0]["method"] == "GET" and paystack.requests[0]["path"] == "/refund/9001"
    )


@pytest.mark.parametrize(
    "status", ["pending", "processing", "processed", "failed", "needs-attention"]
)
def test_every_documented_status_is_passed_through(paystack, status):  # noqa: F811
    paystack.next_response = ok({"id": 1, "status": status, "amount": 1})
    assert paystack.client.fetch_refund("1").status == status


@pytest.mark.parametrize(
    "data",
    [{"status": "pending"}, {"id": 5}, {"id": True, "status": "x"}, {"id": None, "status": "x"}],
)
def test_an_answer_without_an_id_and_status_is_unexpected(paystack, data):  # noqa: F811
    paystack.next_response = ok(data)
    with pytest.raises(PaystackError) as caught:
        paystack.client.fetch_refund("1")
    assert caught.value.retryable is True


@pytest.mark.parametrize(
    ("status", "retryable"), [(500, True), (429, True), (400, False), (404, False), (422, False)]
)
def test_refund_errors_are_classified_like_every_other_call(paystack, status, retryable):  # noqa: F811
    paystack.next_response = (status, {"status": False, "message": "ama@example.com"})
    with pytest.raises(PaystackError) as caught:
        paystack.client.create_refund(
            transaction_reference="r", amount_pesewas=1, currency="GHS", merchant_note="n"
        )
    assert caught.value.retryable is retryable
    assert "ama@example.com" not in str(caught.value)


def test_an_amount_that_is_not_whole_pesewas_reads_as_unknown(paystack):  # noqa: F811
    paystack.next_response = ok({"id": 1, "status": "pending", "amount": "100"})
    assert paystack.client.fetch_refund("1").amount is None


def test_a_refund_id_is_made_safe_for_the_url(paystack):  # noqa: F811
    paystack.next_response = ok({"id": 1, "status": "pending", "amount": 1})
    paystack.client.fetch_refund("a/b?c=d e")
    assert paystack.requests[0]["path"] == "/refund/a%2Fb%3Fc%3Dd%20e"
