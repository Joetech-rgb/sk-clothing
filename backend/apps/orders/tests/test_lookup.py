import pytest
from rest_framework.test import APIClient

from apps.orders.tests.test_expiry import make

pytestmark = pytest.mark.django_db

URL = "/api/v1/orders/lookup/"


def look(reference, phone, client=None):
    return (client or APIClient()).post(
        URL, {"reference": reference, "phone": phone}, format="json"
    )


def test_the_right_reference_and_phone_show_the_order(shop):
    order = make(shop, [(shop.shirt, 2), (shop.shoe, 1)])
    response = look(order.reference, "0241234567")
    assert response.status_code == 200
    data = response.json()
    assert data["reference"] == order.reference
    assert (data["payment_status"], data["fulfilment_status"], data["refund_status"]) == (
        "pending",
        "pending",
        "none",
    )
    assert data["subtotal"]["pesewas"] == 22000 and data["total"]["pesewas"] == 22000
    assert sorted((line["name"], line["quantity"]) for line in data["lines"]) == [
        ("Red shirt - M, Red", 2),
        ("Sneakers - 42", 1),
    ]
    assert response["Cache-Control"] == "no-store"


@pytest.mark.parametrize("phone", ["024 123 4567", "+233241234567", "233241234567", "241234567"])
def test_any_spelling_of_the_phone_number_works(shop, phone):
    order = make(shop)
    assert look(order.reference, phone).status_code == 200


def test_the_reference_may_be_typed_in_lower_case_with_spaces(shop):
    order = make(shop)
    assert look(f"  {order.reference.lower()} ", "0241234567").status_code == 200


def test_nothing_private_is_shown(shop):
    order = make(shop)
    text = look(order.reference, "0241234567").content.decode()
    for secret in (
        "0241234567",
        "+233241234567",
        "Ama Mensah",
        order.idempotency_key,
        "request_hash",
        "reservation",
        "idempotency",
    ):
        assert secret not in text


@pytest.mark.parametrize(
    "case",
    ["wrong phone", "unknown reference", "bad phone", "other customers phone", "empty"],
)
def test_every_kind_of_miss_gets_the_same_answer(shop, case):
    mine = make(shop, phone="0241234567")
    theirs = make(shop, phone="0249999999")
    attempts = {
        "wrong phone": (mine.reference, "0240000000"),
        "unknown reference": ("SKNOSUCHORDER", "0241234567"),
        "bad phone": (mine.reference, "12345"),
        "other customers phone": (theirs.reference, "0241234567"),
        "empty": (mine.reference, "000000000"),
    }
    response = look(*attempts[case])
    assert response.status_code == 404
    assert response.json()["error"]["details"]["reason"] == "order_not_found"
    reference_miss = look("SKNOSUCHORDER", "0241234567")
    assert response.json()["error"]["message"] == reference_miss.json()["error"]["message"]


@pytest.mark.parametrize("body", [{}, {"reference": "x"}, {"phone": "0241234567"}, "nonsense"])
def test_missing_fields_are_refused(shop, body):
    assert APIClient().post(URL, body, format="json").status_code == 400


def test_look_ups_per_address_are_limited(shop, settings):
    settings.CHECKOUT_LIMITS = {
        "lookup_ip_rate": "2/hour",
        "open_orders_per_phone": 100,
        "checkout_ip_rate": "10000/hour",
    }
    order = make(shop)
    client = APIClient()
    codes = [look(order.reference, "0240000000", client).status_code for _ in range(3)]
    assert codes == [404, 404, 429]


def test_only_post_is_allowed(shop):
    assert APIClient().get(URL).status_code == 405


def test_a_cancelled_order_can_still_be_looked_up(shop):
    from apps.orders.services import transition
    from apps.orders.states import Event

    order = make(shop)
    transition(order.pk, Event.CANCEL, actor="test")
    data = look(order.reference, "0241234567").json()
    assert (data["payment_status"], data["fulfilment_status"]) == ("void", "cancelled")
