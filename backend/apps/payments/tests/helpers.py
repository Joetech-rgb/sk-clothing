import json

from rest_framework.test import APIClient

from apps.inventory.models import Reservation, ReservationStatus, StockLevel
from apps.orders.models import Order
from apps.payments.client import fake_paystack
from apps.payments.models import PaymentAttempt
from apps.payments.signature import compute_signature

SECRET = "sk_test_unit_secret"
ORDERS = "/api/v1/orders/"
INITIALIZE = "/api/v1/payments/initialize/"
VERIFY = "/api/v1/payments/verify/"
WEBHOOK = "/api/v1/payments/webhook/paystack/"
EMAIL = "ama@example.com"
_counter = {"n": 0}


def place_order(shop_items, *, method="pickup", phone="0241234567", extra=None):
    """Place an order through the real checkout endpoint. Returns the order JSON."""
    _counter["n"] += 1
    body = {
        "items": [{"variant_id": v, "quantity": q} for v, q in shop_items],
        "delivery": {"method": method, **(extra or {})},
        "contact_name": "Ama Mensah",
        "contact_phone": phone,
        "payment_method": "online",
    }
    response = APIClient().post(
        ORDERS, body, format="json", HTTP_IDEMPOTENCY_KEY=f"pay-test-key-{_counter['n']:06d}"
    )
    assert response.status_code == 201, response.content
    return response.json()


def start(order_reference, email=EMAIL, **headers):
    return APIClient().post(
        INITIALIZE, {"order_reference": order_reference, "email": email}, format="json", **headers
    )


def start_ok(order_reference, email=EMAIL):
    response = start(order_reference, email)
    assert response.status_code == 200, response.content
    return response.json()["reference"]


def verify_page(reference):
    return APIClient().get(VERIFY, {"reference": reference})


def webhook(reference, *, event="charge.success", amount=None, status="success", secret=SECRET):
    body = {
        "event": event,
        "data": {"reference": reference, "status": status, "currency": "GHS"},
    }
    if amount is not None:
        body["data"]["amount"] = amount
    raw = json.dumps(body).encode()
    return APIClient().post(
        WEBHOOK,
        raw,
        content_type="application/json",
        HTTP_X_PAYSTACK_SIGNATURE=compute_signature(raw, secret),
    )


def order_row(order_reference):
    return Order.objects.get(reference=order_reference)


def level(variant_id):
    return StockLevel.objects.get(variant_id=variant_id)


def expire_holds(order_reference):
    """Make the order's stock holds run out, as if 15 minutes passed and the job ran."""
    from apps.inventory import services

    ids = list(order_row(order_reference).reservations.values_list("reservation_id", flat=True))
    return services._release(ids, ReservationStatus.EXPIRED)


def attempts(order_reference):
    return PaymentAttempt.objects.filter(order_id=order_row(order_reference).pk)


def holds_status(order_reference):
    ids = list(order_row(order_reference).reservations.values_list("reservation_id", flat=True))
    return sorted(Reservation.objects.filter(pk__in=ids).values_list("status", flat=True))


def fake():
    return fake_paystack()
