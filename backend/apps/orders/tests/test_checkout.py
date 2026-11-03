import logging
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from apps.delivery import services as delivery
from apps.inventory import services as inventory
from apps.inventory.models import Reservation, ReservationStatus, StockLevel
from apps.orders import checkout
from apps.orders.models import Order, OrderEvent, OrderLine, OrderReservation
from apps.orders.states import check_invariants

pytestmark = pytest.mark.django_db

URL = "/api/v1/orders/"
PHONE = "0241234567"
E164 = "+233241234567"
ACCRA = {"latitude": 5.61, "longitude": -0.19, "address": "12 Oak Street, Osu"}
KUMASI = {"latitude": 6.6885, "longitude": -1.6244, "address": "Adum, Kumasi"}
User = get_user_model()


def body(items, method="pickup", *, phone=PHONE, name="Ama Mensah", cod=False, **delivery_extra):
    return {
        "items": [{"variant_id": v, "quantity": q} for v, q in items],
        "delivery": {"method": method, **delivery_extra},
        "contact_name": name,
        "contact_phone": phone,
        "payment_method": "cod" if cod else "online",
    }


def place(client, data, key="key-0000001", **headers):
    return client.post(URL, data, format="json", HTTP_IDEMPOTENCY_KEY=key, **headers)


def reason(response):
    return response.json()["error"]["details"]["reason"]


def held(variant_id):
    return StockLevel.objects.get(variant_id=variant_id).reserved


# --- a normal order ---------------------------------------------------------------------------


def test_an_order_is_created_with_server_prices_and_stock_held(shop):
    response = place(APIClient(), body([(shop.shirt, 2), (shop.shoe, 1)]))
    assert response.status_code == 201
    data = response.json()
    assert data["replayed"] is False and data["reference"].startswith("SK")
    assert data["subtotal"]["pesewas"] == 2 * 5000 + 12000
    assert data["delivery_fee"]["pesewas"] == 0
    assert data["total"]["pesewas"] == 22000
    assert (data["payment_status"], data["fulfilment_status"]) == ("pending", "pending")
    assert data["pickup"] is True
    order = Order.objects.get()
    assert order.contact_phone == E164 and order.contact_name == "Ama Mensah"
    lines = {line.variant_id: line for line in order.lines.all()}
    assert lines[shop.shirt].quantity == 2 and lines[shop.shirt].unit_price_pesewas == 5000
    assert lines[shop.shirt].line_total_pesewas == 10000
    assert (
        lines[shop.shirt].name == "Red shirt - M, Red" and lines[shop.shoe].name == "Sneakers - 42"
    )
    assert held(shop.shirt) == 2 and held(shop.shoe) == 1
    assert order.reservations.count() == 2
    assert [e.event for e in order.events.all()] == ["created"]
    assert check_invariants(order.state) == []
    assert inventory.verify_ledger(shop.shirt) == []


def test_stock_is_held_for_about_fifteen_minutes(shop):
    before = timezone.now()
    data = place(APIClient(), body([(shop.shirt, 1)])).json()
    held_until = timezone.datetime.fromisoformat(data["stock_held_until"].replace("Z", "+00:00"))
    assert (
        timedelta(minutes=14, seconds=50) < held_until - before < timedelta(minutes=15, seconds=10)
    )


def test_the_browser_can_never_name_a_price(shop):
    data = body([(shop.shirt, 2)])
    data["items"][0]["unit_price"] = 1
    data["items"][0]["line_total"] = 2
    data["subtotal"] = 3
    data["total"] = 3
    data["delivery"]["fee"] = 0
    data["delivery"]["method"] = "station"
    data["delivery"]["station_name"] = "Kumasi STC"
    response = place(APIClient(), data)
    assert response.status_code == 201
    assert response.json()["total"]["pesewas"] == 10000 + 2500
    assert OrderLine.objects.get().unit_price_pesewas == 5000


def test_repeated_variants_are_added_together(shop):
    response = place(APIClient(), body([(shop.shirt, 1), (shop.shirt, 2)]))
    assert response.status_code == 201
    (line,) = OrderLine.objects.all()
    assert line.quantity == 3
    assert held(shop.shirt) == 3 and Reservation.objects.count() == 1


# --- delivery ---------------------------------------------------------------------------------


def test_station_delivery_uses_the_station_fee_ignoring_case_and_spacing(shop):
    data = body([(shop.shirt, 1)], "station", station_name="  kumasi   stc ")
    response = place(APIClient(), data)
    assert response.status_code == 201
    assert response.json()["delivery_fee"]["pesewas"] == 2500
    assert Order.objects.get().delivery_details == {"station_name": "kumasi stc"}


def test_an_unlisted_station_waits_for_a_quote(shop):
    response = place(APIClient(), body([(shop.shirt, 1)], "station", station_name="Tamale"))
    data = response.json()
    assert response.status_code == 201
    assert data["fulfilment_status"] == "awaiting_quote"
    assert data["delivery_fee"] is None and data["total"] is None
    assert Order.objects.get().delivery_details["quote_reason"] == "unlisted_station"
    assert held(shop.shirt) == 1  # stock is still held while staff quote


def test_doorstep_inside_the_radius_is_priced_by_the_distance_rule(shop):
    response = place(APIClient(), body([(shop.shirt, 1)], "doorstep", **ACCRA))
    expected = delivery.get_quote("doorstep", latitude=5.61, longitude=-0.19).fee.pesewas
    assert response.status_code == 201
    assert response.json()["delivery_fee"]["pesewas"] == expected >= 1000
    details = Order.objects.get().delivery_details
    assert details["address"] == "12 Oak Street, Osu" and "road_km" in details


def test_doorstep_beyond_the_maximum_distance_waits_for_a_quote(shop):
    response = place(APIClient(), body([(shop.shirt, 1)], "doorstep", **KUMASI))
    assert response.json()["fulfilment_status"] == "awaiting_quote"
    assert Order.objects.get().delivery_details["quote_reason"] == "beyond_max_distance"


def test_doorstep_with_no_delivery_settings_waits_for_a_quote(shop):
    from apps.delivery.models import DeliverySettings

    DeliverySettings.objects.all().delete()
    response = place(APIClient(), body([(shop.shirt, 1)], "doorstep", **ACCRA))
    assert response.json()["fulfilment_status"] == "awaiting_quote"


def test_pay_on_delivery_is_allowed_only_for_a_priced_doorstep_order(shop):
    ok = place(
        APIClient(), body([(shop.shirt, 1)], "doorstep", cod=True, **ACCRA), key="key-cod-ok1"
    )
    assert ok.status_code == 201 and ok.json()["payment_status"] == "cod_pending"
    cases = [
        body([(shop.shirt, 1)], "pickup", cod=True),
        body([(shop.shirt, 1)], "station", cod=True, station_name="Kumasi STC"),
        body([(shop.shirt, 1)], "doorstep", cod=True, **KUMASI),
        body([(shop.shirt, 1)], "station", cod=True, station_name="Tamale"),
    ]
    for n, data in enumerate(cases):
        refused = place(APIClient(), data, key=f"key-cod-no{n}")
        assert refused.status_code == 400 and reason(refused) == "cod_not_available"
    assert Order.objects.count() == 1 and held(shop.shirt) == 1


# --- retrying safely --------------------------------------------------------------------------


def test_the_same_key_and_request_returns_the_same_order_and_holds_stock_once(shop):
    client = APIClient()
    first = place(client, body([(shop.shirt, 2)]))
    second = place(client, body([(shop.shirt, 2)]))
    third = place(client, body([(shop.shirt, 2)]))
    assert (first.status_code, second.status_code, third.status_code) == (201, 200, 200)
    assert second.json()["reference"] == first.json()["reference"]
    assert second.json()["replayed"] is True and first.json()["replayed"] is False
    assert second.json()["stock_held_until"] == first.json()["stock_held_until"]
    assert Order.objects.count() == 1 and OrderEvent.objects.count() == 1
    assert Reservation.objects.count() == 1 and held(shop.shirt) == 2


def test_spelling_the_same_request_differently_is_still_a_retry(shop):
    place(APIClient(), body([(shop.shirt, 3)], phone="0241234567", name="Ama"))
    again = place(
        APIClient(),
        body([(shop.shirt, 1), (shop.shirt, 2)], phone="+233 24 123 4567", name=" Ama "),
    )
    assert again.status_code == 200 and Order.objects.count() == 1


@pytest.mark.parametrize(
    "change",
    [
        lambda s: body([(s.shirt, 3)]),
        lambda s: body([(s.shirt, 2), (s.shoe, 1)]),
        lambda s: body([(s.shirt, 2)], phone="0249999999"),
        lambda s: body([(s.shirt, 2)], name="Someone Else"),
        lambda s: body([(s.shirt, 2)], "station", station_name="Kumasi STC"),
        lambda s: body([(s.shirt, 2)], cod=False, method="doorstep", **ACCRA),
    ],
)
def test_the_same_key_with_a_different_request_is_refused_and_changes_nothing(shop, change):
    place(APIClient(), body([(shop.shirt, 2)]))
    refused = place(APIClient(), change(shop))
    assert refused.status_code == 409 and reason(refused) == "idempotency_conflict"
    assert Order.objects.count() == 1 and held(shop.shirt) == 2
    assert Reservation.objects.count() == 1


@pytest.mark.parametrize("key", [None, "", "short", "has space in it", "a" * 65, "bad/slash/key1"])
def test_a_missing_or_malformed_idempotency_key_is_refused(shop, key):
    headers = {} if key is None else {"HTTP_IDEMPOTENCY_KEY": key}
    response = APIClient().post(URL, body([(shop.shirt, 1)]), format="json", **headers)
    assert response.status_code == 400 and reason(response) == "idempotency_key_required"
    assert Order.objects.count() == 0 and held(shop.shirt) == 0


def test_keys_are_scoped_to_the_customer(shop):
    ama = User.objects.create_user(email="ama@example.com", password="pw-12345-xyz")
    kofi = User.objects.create_user(email="kofi@example.com", password="pw-12345-xyz")
    results = {}
    for name, user in (("guest", None), ("ama", ama), ("kofi", kofi)):
        client = APIClient()
        if user:
            client.force_login(user)
        results[name] = place(client, body([(shop.shirt, 1)]), key="shared-key-123")
        assert results[name].status_code == 201
    assert len({r.json()["reference"] for r in results.values()}) == 3
    assert Order.objects.count() == 3
    assert set(Order.objects.values_list("user_id", flat=True)) == {None, ama.pk, kofi.pk}
    again = APIClient()
    again.force_login(ama)
    assert (
        place(again, body([(shop.shirt, 1)]), key="shared-key-123").json()["reference"]
        == (results["ama"].json()["reference"])
    )


def test_the_raw_key_is_never_stored(shop):
    place(APIClient(), body([(shop.shirt, 1)]), key="my-secret-key-1")
    order = Order.objects.get()
    assert "my-secret-key-1" not in order.idempotency_key and len(order.idempotency_key) == 48
    assert not Reservation.objects.filter(idempotency_key__contains="my-secret-key-1").exists()


# --- stock ------------------------------------------------------------------------------------


def test_not_enough_stock_refuses_the_order_and_holds_nothing(shop):
    refused = place(APIClient(), body([(shop.scarce, 2)]))
    assert refused.status_code == 409 and reason(refused) == "insufficient_stock"
    details = refused.json()["error"]["details"]
    assert details["variant_id"] == shop.scarce and details["available"] == 1
    assert Order.objects.count() == 0 and held(shop.scarce) == 0


def test_an_item_with_no_stock_is_refused(shop):
    refused = place(APIClient(), body([(shop.empty, 1)]))
    assert refused.status_code == 409 and reason(refused) == "insufficient_stock"


def test_an_order_is_all_or_nothing_across_items(shop):
    refused = place(APIClient(), body([(shop.shirt, 1), (shop.scarce, 5)]))
    assert refused.status_code == 409
    assert held(shop.shirt) == 0 and held(shop.scarce) == 0
    assert Reservation.objects.count() == 0 and Order.objects.count() == 0


def test_stock_already_held_by_another_order_is_not_available(shop):
    assert place(APIClient(), body([(shop.scarce, 1)]), key="key-first-001").status_code == 201
    second = place(APIClient(), body([(shop.scarce, 1)], phone="0249999999"), key="key-second-02")
    assert second.status_code == 409 and Order.objects.count() == 1


@pytest.mark.parametrize("which", ["cap", "missing"])
def test_items_that_cannot_be_sold_are_refused(shop, which):
    variant = shop.cap if which == "cap" else 999999
    refused = place(APIClient(), body([(variant, 1)]))
    assert refused.status_code == 422 and reason(refused) == "variant_unavailable"
    assert refused.json()["error"]["details"]["variant_id"] == variant
    assert Order.objects.count() == 0


def test_a_failure_after_the_hold_undoes_the_hold(shop, monkeypatch):
    def explode(**kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(checkout, "create_order", explode)
    request = checkout.CheckoutRequest(
        items=((shop.shirt, 2),), delivery_method="pickup", contact_name="Ama", contact_phone=E164
    )
    with pytest.raises(RuntimeError):
        checkout.checkout(request, idempotency_key="key-boom-0001", user_id=None)
    assert held(shop.shirt) == 0 and Reservation.objects.count() == 0
    assert Order.objects.count() == 0 and OrderReservation.objects.count() == 0


def test_expired_holds_do_not_block_a_new_order(shop):
    place(APIClient(), body([(shop.scarce, 1)]), key="key-first-001")
    Reservation.objects.update(expires_at=timezone.now() - timedelta(minutes=1))
    assert inventory_expire() == 1
    second = place(APIClient(), body([(shop.scarce, 1)], phone="0249999999"), key="key-second-02")
    assert second.status_code == 201


def inventory_expire():
    from apps.inventory import services

    ids = list(
        Reservation.objects.filter(
            status=ReservationStatus.ACTIVE, expires_at__lte=timezone.now()
        ).values_list("id", flat=True)
    )
    return services._release(ids, ReservationStatus.EXPIRED)


# --- who is ordering --------------------------------------------------------------------------


def test_a_signed_in_customer_owns_the_order_and_a_guest_does_not(shop):
    user = User.objects.create_user(email="ama@example.com", password="pw-12345-xyz")
    signed_in = APIClient()
    signed_in.force_login(user)
    assert place(signed_in, body([(shop.shirt, 1)]), key="key-user-0001").status_code == 201
    assert place(APIClient(), body([(shop.shirt, 1)]), key="key-guest-001").status_code == 201
    owners = list(Order.objects.order_by("id").values_list("user_id", flat=True))
    assert owners == [user.pk, None]
    assert Order.objects.first().events.get().actor == "guest"
    assert Order.objects.last().events.get().actor == f"user:{user.pk}"


def test_a_switched_off_account_orders_as_a_guest(shop):
    user = User.objects.create_user(email="gone@example.com", password="pw-12345-xyz")
    client = APIClient()
    client.force_login(user)
    User.objects.filter(pk=user.pk).update(is_active=False)
    assert place(client, body([(shop.shirt, 1)])).status_code == 201
    assert Order.objects.get().user_id is None


# --- limits -----------------------------------------------------------------------------------


def test_one_number_cannot_tie_up_stock_with_many_unpaid_orders(shop, settings):
    settings.CHECKOUT_LIMITS = {"open_orders_per_phone": 3, "checkout_ip_rate": "10000/hour"}
    codes = [place(APIClient(), body([(shop.shirt, 1)]), key=f"key-open-{n:04d}") for n in range(5)]
    assert [r.status_code for r in codes] == [201, 201, 201, 429, 429]
    assert reason(codes[3]) == "too_many_open_orders"
    assert Order.objects.count() == 3 and held(shop.shirt) == 3
    other = place(APIClient(), body([(shop.shirt, 1)], phone="0249999999"), key="key-other-001")
    assert other.status_code == 201  # another number is not affected


def test_a_retry_is_never_blocked_by_the_open_order_limit(shop, settings):
    settings.CHECKOUT_LIMITS = {"open_orders_per_phone": 1, "checkout_ip_rate": "10000/hour"}
    assert place(APIClient(), body([(shop.shirt, 1)])).status_code == 201
    assert place(APIClient(), body([(shop.shirt, 1)])).status_code == 200


def test_old_unpaid_orders_stop_counting_after_the_hold_window(shop, settings):
    settings.CHECKOUT_LIMITS = {"open_orders_per_phone": 1, "checkout_ip_rate": "10000/hour"}
    place(APIClient(), body([(shop.shirt, 1)]), key="key-open-0001")
    assert place(APIClient(), body([(shop.shirt, 1)]), key="key-open-0002").status_code == 429
    Order.objects.update(created_at=timezone.now() - timedelta(minutes=16))
    assert place(APIClient(), body([(shop.shirt, 1)]), key="key-open-0003").status_code == 201


def test_paid_orders_do_not_count_as_open(shop, settings):
    from apps.orders.services import transition
    from apps.orders.states import Event

    settings.CHECKOUT_LIMITS = {"open_orders_per_phone": 1, "checkout_ip_rate": "10000/hour"}
    place(APIClient(), body([(shop.shirt, 1)]), key="key-open-0001")
    transition(Order.objects.get().pk, Event.PAYMENT_CONFIRMED, actor="test")
    assert place(APIClient(), body([(shop.shirt, 1)]), key="key-open-0002").status_code == 201


def test_checkouts_per_address_are_limited(shop, settings):
    settings.CHECKOUT_LIMITS = {"checkout_ip_rate": "2/hour", "open_orders_per_phone": 100}
    statuses = [
        place(APIClient(), body([(shop.shirt, 1)]), key=f"key-rate-{n:04d}").status_code
        for n in range(3)
    ]
    assert statuses == [201, 201, 429]
    assert Order.objects.count() == 2


# --- validation and cross-site protection -----------------------------------------------------


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.update(items=[]),
        lambda d: d.update(items=[{"variant_id": 1, "quantity": 0}]),
        lambda d: d.update(items=[{"variant_id": 1, "quantity": -2}]),
        lambda d: d.update(items=[{"variant_id": 1, "quantity": 1001}]),
        lambda d: d.update(items=[{"variant_id": 0, "quantity": 1}]),
        lambda d: d.update(items=[{"variant_id": 1, "quantity": 1}] * 51),
        lambda d: d.update(items="nonsense"),
        lambda d: d.pop("items"),
        lambda d: d.update(contact_phone="12345"),
        lambda d: d.update(contact_phone="+441234567890"),
        lambda d: d.update(contact_name=""),
        lambda d: d.update(payment_method="bitcoin"),
        lambda d: d.update(delivery={"method": "teleport"}),
        lambda d: d.update(delivery={"method": "station"}),
        lambda d: d.update(delivery={"method": "station", "station_name": "  "}),
        lambda d: d.update(delivery={"method": "doorstep", "address": "x"}),
        lambda d: d.update(delivery={"method": "doorstep", "latitude": 5.6, "longitude": -0.2}),
        lambda d: d.update(
            delivery={"method": "doorstep", "latitude": 95, "longitude": 0, "address": "x"}
        ),
        lambda d: d.pop("delivery"),
    ],
)
def test_bad_input_is_refused_and_changes_nothing(shop, mutate):
    data = body([(shop.shirt, 1)])
    mutate(data)
    response = place(APIClient(), data)
    assert response.status_code == 400
    assert Order.objects.count() == 0 and Reservation.objects.count() == 0


def test_two_thousand_of_one_item_across_lines_is_refused(shop):
    refused = place(APIClient(), body([(shop.shirt, 900), (shop.shirt, 900)]))
    assert refused.status_code == 400 and Order.objects.count() == 0


def test_only_json_is_accepted(shop):
    response = APIClient().post(
        URL,
        "items=1",
        content_type="application/x-www-form-urlencoded",
        HTTP_IDEMPOTENCY_KEY="key-0000001",
    )
    assert response.status_code == 415


@pytest.mark.parametrize("origin", ["https://evil.example", "null"])
def test_a_cross_site_page_cannot_place_an_order(shop, origin):
    refused = place(APIClient(), body([(shop.shirt, 1)]), HTTP_ORIGIN=origin)
    assert refused.status_code == 403 and reason(refused) == "bad_origin"
    assert Order.objects.count() == 0 and held(shop.shirt) == 0


def test_the_storefront_origin_is_accepted(shop):
    ok = place(APIClient(), body([(shop.shirt, 1)]), HTTP_ORIGIN="https://www.example-shop.test")
    assert ok.status_code == 201


def test_responses_are_never_cached(shop):
    assert place(APIClient(), body([(shop.shirt, 1)]))["Cache-Control"] == "no-store"


def test_the_order_response_leaks_no_internal_ids_or_contact_details(shop):
    text = place(APIClient(), body([(shop.shirt, 1)])).content.decode()
    for secret in (PHONE, E164, "Ama Mensah", "reservation", "idempotency"):
        assert secret not in text


def test_names_numbers_and_addresses_never_reach_the_logs(shop, caplog):
    caplog.set_level(logging.DEBUG)
    place(APIClient(), body([(shop.shirt, 1)], "doorstep", name="Ama Mensah", **ACCRA))
    place(
        APIClient(),
        body([(shop.shirt, 99)], "doorstep", name="Ama Mensah", **ACCRA),
        key="key-0000002",
    )
    text = "\n".join(f"{r.getMessage()} {r.args}" for r in caplog.records)
    for secret in ("Ama Mensah", PHONE, E164, "241234567", "Oak Street", "key-0000001"):
        assert secret not in text
    assert "placed" in text
