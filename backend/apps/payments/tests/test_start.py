import logging

import pytest
from rest_framework.test import APIClient

from apps.orders import services as order_services
from apps.orders.models import Order
from apps.orders.states import Event
from apps.payments.client import PaystackError
from apps.payments.models import PaymentAttempt
from apps.payments.tests.helpers import (
    EMAIL,
    INITIALIZE,
    attempts,
    fake,
    order_row,
    place_order,
    start,
    start_ok,
)

pytestmark = pytest.mark.django_db


def reason(response):
    return response.json()["error"]["details"]["reason"]


def test_starting_a_payment_charges_the_order_total_and_nothing_else(shop):
    order = place_order([(shop.shirt, 2)], method="station", extra={"station_name": "Kumasi STC"})
    response = APIClient().post(
        INITIALIZE,
        {
            "order_reference": order["reference"],
            "email": " Ama@Example.COM ",
            "amount": 1,
            "amount_pesewas": 1,
        },
        format="json",
    )
    assert response.status_code == 200
    reference = response.json()["reference"]
    assert response.json()["authorization_url"] == f"https://checkout.example/{reference}"
    assert reference.startswith(order["reference"] + "-")
    expected = 2 * 5000 + 2500
    assert fake().initialized[reference]["amount"] == expected
    attempt = PaymentAttempt.objects.get(reference=reference)
    assert attempt.amount_pesewas == expected and attempt.currency == "GHS"
    assert attempt.status == "pending" and attempt.payer_email == "ama@example.com"
    assert fake().initialized[reference]["email"] == "ama@example.com"
    assert response["Cache-Control"] == "no-store"


def test_each_attempt_gets_its_own_unguessable_reference(shop):
    order = place_order([(shop.shirt, 1)])
    references = {start_ok(order["reference"]) for _ in range(4)}
    assert len(references) == 4


def test_the_callback_address_is_passed_on_when_configured(shop, settings):
    settings.PAYSTACK_CALLBACK_URL = "https://www.example-shop.test/paid"
    reference = start_ok(place_order([(shop.shirt, 1)])["reference"])
    assert fake().initialized[reference]["callback_url"] == "https://www.example-shop.test/paid"


def test_an_unknown_order_is_not_found(shop):
    response = start("SKNOSUCHORD")
    assert response.status_code == 404 and reason(response) == "order_not_found"
    assert PaymentAttempt.objects.count() == 0


@pytest.mark.parametrize(
    ("make", "why"),
    [
        (
            lambda s: place_order(
                [(s.shirt, 1)], method="station", extra={"station_name": "Tamale"}
            ),
            "awaiting_quote",
        ),
        (lambda s: _cod(s), "pay_on_delivery"),
        (lambda s: _paid(s), "already_paid"),
        (lambda s: _cancelled(s), "order_closed"),
    ],
)
def test_orders_that_cannot_be_paid_online_are_refused(shop, make, why):
    order = make(shop)
    response = start(order["reference"])
    assert response.status_code == 409 and reason(response) == "order_not_payable"
    assert response.json()["error"]["details"]["why"] == why
    assert PaymentAttempt.objects.filter(order_id=order_row(order["reference"]).pk).count() == (
        1 if why == "already_paid" else 0
    )
    assert fake().initialized == ({} if why != "already_paid" else fake().initialized)


def _cod(shop):
    from apps.payments.tests import helpers

    helpers._counter["n"] += 1
    response = APIClient().post(
        "/api/v1/orders/",
        {
            "items": [{"variant_id": shop.shirt, "quantity": 1}],
            "delivery": {
                "method": "doorstep",
                "latitude": 5.61,
                "longitude": -0.19,
                "address": "12 Oak Street",
            },
            "contact_name": "Ama",
            "contact_phone": "0241234567",
            "payment_method": "cod",
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY=f"cod-test-key-{helpers._counter['n']:06d}",
    )
    assert response.status_code == 201
    return response.json()


def _paid(shop):
    order = place_order([(shop.shirt, 1)])
    reference = start_ok(order["reference"])
    from apps.payments.tests.helpers import verify_page

    assert verify_page(reference).status_code == 200
    assert order_row(order["reference"]).payment == "paid"
    return order


def _cancelled(shop):
    order = place_order([(shop.shirt, 1)])
    order_services.transition(order_row(order["reference"]).pk, Event.CANCEL, actor="test")
    return order


@pytest.mark.parametrize("email", ["", "not-an-email", "a@", "@b.com", "x" * 250 + "@example.com"])
def test_a_bad_email_is_refused(shop, email):
    order = place_order([(shop.shirt, 1)])
    response = start(order["reference"], email)
    assert response.status_code == 400
    assert PaymentAttempt.objects.count() == 0


@pytest.mark.parametrize("body", [{}, {"email": EMAIL}, {"order_reference": "SKX"}, "nonsense"])
def test_missing_fields_are_refused(shop, body):
    assert APIClient().post(INITIALIZE, body, format="json").status_code == 400


def test_only_json_is_accepted(shop):
    response = APIClient().post(
        INITIALIZE, "order_reference=x", content_type="application/x-www-form-urlencoded"
    )
    assert response.status_code == 415


def test_an_order_can_be_tried_a_limited_number_of_times(shop):
    order = place_order([(shop.shirt, 1)])
    codes = [start(order["reference"]).status_code for _ in range(7)]
    assert codes == [200] * 5 + [429, 429]
    assert reason(start(order["reference"])) == "too_many_payment_attempts"
    assert attempts(order["reference"]).count() == 5


def test_a_failed_attempt_can_be_followed_by_another(shop):
    order = place_order([(shop.shirt, 1)])
    first = start_ok(order["reference"])
    fake().set_outcome(first, status="failed")
    from apps.payments.tests.helpers import verify_page

    assert verify_page(first).json()["payment_status"] == "failed"
    second = start_ok(order["reference"])  # "failed" orders may be paid for again
    assert second != first and PaymentAttempt.objects.count() == 2


def test_when_paystack_is_down_the_attempt_is_marked_failed_and_the_order_is_unchanged(shop):
    order = place_order([(shop.shirt, 1)])
    fake().fail_initialize = PaystackError("down", retryable=True)
    response = start(order["reference"])
    assert response.status_code == 503 and reason(response) == "payment_unavailable"
    (attempt,) = attempts(order["reference"])
    assert attempt.status == "failed"
    assert order_row(order["reference"]).payment == "pending"
    fake().fail_initialize = None
    assert start(order["reference"]).status_code == 200


def test_with_no_paystack_key_payment_is_unavailable(shop, settings):
    settings.PAYSTACK_CLIENT = ""
    settings.PAYSTACK_SECRET_KEY = ""
    response = start(place_order([(shop.shirt, 1)])["reference"])
    assert response.status_code == 503 and reason(response) == "payment_unavailable"
    assert PaymentAttempt.objects.count() == 0


@pytest.mark.parametrize("origin", ["https://evil.example", "null"])
def test_a_cross_site_page_cannot_start_a_payment(shop, origin):
    order = place_order([(shop.shirt, 1)])
    response = start(order["reference"], HTTP_ORIGIN=origin)
    assert response.status_code == 403 and reason(response) == "bad_origin"
    assert PaymentAttempt.objects.count() == 0 and fake().initialized == {}


def test_starts_per_address_are_limited(shop, settings):
    settings.PAYMENT_LIMITS = {"start_ip_rate": "2/hour", "verify_ip_rate": "10000/hour"}
    order = place_order([(shop.shirt, 1)])
    assert [start(order["reference"]).status_code for _ in range(3)] == [200, 200, 429]


def test_the_email_never_reaches_the_logs_or_the_answer(shop, caplog):
    caplog.set_level(logging.DEBUG)
    order = place_order([(shop.shirt, 1)])
    response = start(order["reference"], "secret.person@example.com")
    text = response.content.decode() + "\n".join(r.getMessage() for r in caplog.records)
    assert "secret.person" not in text
    assert Order.objects.get().contact_phone not in text
