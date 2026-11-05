import itertools
import logging
from concurrent.futures import ThreadPoolExecutor

import pytest
from django.contrib.auth.models import Permission
from django.db import connection
from django.urls import reverse
from rest_framework.test import APIClient

from apps.delivery import code_services as codes
from apps.delivery.models import DeliveryCode, DeliveryCodeEvent
from apps.identity.models import User
from apps.orders import services
from apps.orders.models import Order
from apps.orders.services import LineInput, create_order, transition
from apps.orders.states import Event
from apps.orders.views import order_json

ORIGIN = "https://www.example-shop.test"  # the trusted origin set in this folder's conftest
PHONE = "+233201234567"  # a made-up number
_numbers = itertools.count(1)


def make_order(*, cod=False, upto="dispatched"):
    """An order taken through the real transitions as far as `upto`: paid, packed or dispatched."""
    line = LineInput(
        variant_id=1,
        name="Test shirt",
        quantity=1,
        tier="retail",
        unit_price_pesewas=5000,
        list_price_pesewas=5000,
        tier_price_pesewas=5000,
        source="tier",
    )
    order, _ = create_order(
        idempotency_key=f"delivery-test-{next(_numbers):04d}",
        lines=[line],
        delivery_method="station",
        delivery_fee_pesewas=1000,
        cod=cod,
        contact_phone=PHONE,
    )
    steps = [Event.COD_CONFIRMED if cod else Event.PAYMENT_CONFIRMED, Event.PACKED]
    steps.append(Event.DISPATCHED)
    for step in steps[: {"paid": 1, "packed": 2, "dispatched": 3}[upto]]:
        transition(order.pk, step, actor="system:test")
    order.refresh_from_db()
    return order


def wrong_for(code):
    return "000000" if code != "000000" else "111111"


def make_user(*, can_confirm):
    user = User.objects.create_user(
        email=f"user{next(_numbers)}@example.test", password="not-a-real-password"
    )
    if can_confirm:
        user.user_permissions.add(
            Permission.objects.get(content_type__app_label="delivery", codename="confirm_delivery")
        )
    return user


def post_code(client, order, code):
    return client.post(
        reverse("orders-delivery-confirm", kwargs={"reference": order.reference}),
        {"code": code},
        format="json",
        HTTP_ORIGIN=ORIGIN,
    )


@pytest.fixture
def order(db):
    return make_order()


@pytest.fixture
def code(order):
    return codes.issue_delivery_code(order.pk, actor="system:test")


# --- the service ---------------------------------------------------------------------------


def test_the_right_code_delivers_the_order_and_records_who_and_when(order, code):
    result = services.confirm_delivery(order.reference, code, actor="user:7")
    assert result.status == services.DELIVERED_OK
    order.refresh_from_db()
    assert order.fulfilment == "delivered"
    assert order.delivered_at is not None and result.delivered_at == order.delivered_at
    last = order.events.last()
    assert (last.event, last.actor) == ("delivered", "user:7")
    row = DeliveryCode.objects.get(order_id=order.pk)
    assert row.confirmed_by == "user:7" and row.verified_at is not None


def test_a_pay_on_delivery_order_becomes_paid_when_the_code_is_entered(db):
    order = make_order(cod=True)
    code = codes.issue_delivery_code(order.pk, actor="system:test")
    assert order.payment == "cod_confirmed"
    services.confirm_delivery(order.reference, code, actor="user:7")
    order.refresh_from_db()
    assert (order.payment, order.fulfilment) == ("paid", "delivered")


def test_a_wrong_code_is_refused_and_the_attempt_is_kept(order, code):
    result = services.confirm_delivery(order.reference, wrong_for(code), actor="user:7")
    assert result.status == services.WRONG_CODE
    assert DeliveryCode.objects.get(order_id=order.pk).failed_attempts == 1
    order.refresh_from_db()
    assert order.fulfilment == "out_for_delivery" and order.delivered_at is None


def test_five_wrong_codes_lock_it_even_against_the_right_one(order, code):
    for _ in range(5):
        services.confirm_delivery(order.reference, wrong_for(code), actor="user:7")
    result = services.confirm_delivery(order.reference, code, actor="user:7")
    assert result.status == services.CODE_LOCKED
    order.refresh_from_db()
    assert order.fulfilment == "out_for_delivery"


def test_input_that_is_not_six_digits_uses_no_attempt(order, code):
    result = services.confirm_delivery(order.reference, "12", actor="user:7")
    assert result.status == services.MALFORMED_CODE
    assert DeliveryCode.objects.get(order_id=order.pk).failed_attempts == 0


def test_repeating_a_correct_code_changes_nothing(order, code):
    first = services.confirm_delivery(order.reference, code, actor="user:7")
    second = services.confirm_delivery(order.reference, code, actor="user:8")
    assert (first.status, second.status) == (services.DELIVERED_OK, services.ALREADY_DELIVERED)
    assert second.delivered_at == first.delivered_at
    assert DeliveryCode.objects.get(order_id=order.pk).confirmed_by == "user:7"
    assert order.events.filter(event="delivered").count() == 1


def test_an_order_that_is_not_out_for_delivery_cannot_be_confirmed(db):
    order = make_order(upto="packed")
    code = codes.issue_delivery_code(order.pk, actor="system:test")
    result = services.confirm_delivery(order.reference, code, actor="user:7")
    assert result.status == services.NOT_OUT_FOR_DELIVERY
    assert DeliveryCode.objects.get(order_id=order.pk).failed_attempts == 0


def test_an_order_with_no_code_issued_cannot_be_confirmed(order):
    result = services.confirm_delivery(order.reference, "123456", actor="user:7")
    assert result.status == services.NO_DELIVERY_CODE


def test_an_unknown_reference_is_not_found(db):
    result = services.confirm_delivery("SKNOSUCHREF", "123456", actor="user:7")
    assert result.status == services.ORDER_NOT_FOUND


def test_any_path_to_delivered_records_the_time_once(order):
    transition(order.pk, Event.DELIVERED, actor="user:7")
    order.refresh_from_db()
    first_time = order.delivered_at
    assert first_time is not None
    transition(order.pk, Event.DELIVERED, actor="user:8")  # a repeat is a no-op
    order.refresh_from_db()
    assert order.delivered_at == first_time


def test_issuing_twice_gives_the_same_code_and_one_history_line(order):
    first = codes.issue_delivery_code(order.pk, actor="system:test")
    second = codes.issue_delivery_code(order.pk, actor="system:test")
    assert first == second
    assert DeliveryCodeEvent.objects.filter(order_id=order.pk, kind="issued").count() == 1


def test_the_stored_row_does_not_contain_the_code(order, code):
    row = DeliveryCode.objects.get(order_id=order.pk)
    stored = f"{row.nonce} {row.confirmed_by} {row!s}"
    assert code not in stored


def test_staff_can_reissue_a_locked_code_and_the_new_one_works(order, code):
    for _ in range(5):
        services.confirm_delivery(order.reference, wrong_for(code), actor="user:7")
    new_code = codes.reissue_delivery_code(order.pk, actor="user:1")
    row = DeliveryCode.objects.get(order_id=order.pk)
    assert (row.failed_attempts, row.locked, row.issue_number) == (0, False, 2)
    result = services.confirm_delivery(order.reference, new_code, actor="user:7")
    assert result.status == services.DELIVERED_OK
    kinds = list(DeliveryCodeEvent.objects.filter(order_id=order.pk).values_list("kind", flat=True))
    assert kinds == ["issued", "wrong", "wrong", "wrong", "wrong", "locked", "reissued", "verified"]


def test_a_code_that_was_used_cannot_be_reissued(order, code):
    services.confirm_delivery(order.reference, code, actor="user:7")
    with pytest.raises(codes.CodeAlreadyUsed):
        codes.reissue_delivery_code(order.pk, actor="user:1")


def test_reissuing_when_no_code_exists_is_refused(order):
    with pytest.raises(codes.CodeNotIssued):
        codes.reissue_delivery_code(order.pk, actor="user:1")


def test_the_code_is_never_logged(order, code, caplog):
    with caplog.at_level(logging.DEBUG):
        services.confirm_delivery(order.reference, wrong_for(code), actor="user:7")
        services.confirm_delivery(order.reference, code, actor="user:7")
    assert code not in caplog.text


# --- the order page ------------------------------------------------------------------------


def test_the_order_page_shows_the_code_only_while_out_for_delivery(order, code):
    page = order_json(order)
    assert page["delivery_code"] == code and page["delivery_code_locked"] is False

    packed = make_order(upto="packed")
    codes.issue_delivery_code(packed.pk, actor="system:test")
    assert order_json(packed)["delivery_code"] is None  # not dispatched yet

    services.confirm_delivery(order.reference, code, actor="user:7")
    order.refresh_from_db()
    assert order_json(order)["delivery_code"] is None  # delivered: nothing left to show


def test_a_locked_code_is_not_shown_and_is_flagged(order, code):
    for _ in range(5):
        services.confirm_delivery(order.reference, wrong_for(code), actor="user:7")
    page = order_json(order)
    assert page["delivery_code"] is None and page["delivery_code_locked"] is True


# --- the endpoint --------------------------------------------------------------------------


def test_a_rider_can_confirm_a_delivery(order, code):
    rider = make_user(can_confirm=True)
    client = APIClient()
    client.force_login(rider)
    response = post_code(client, order, code)
    assert response.status_code == 200
    order.refresh_from_db()
    assert order.fulfilment == "delivered"
    assert order.events.last().actor == f"user:{rider.pk}"


def test_a_customer_without_the_permission_is_refused_and_uses_no_attempt(order, code):
    client = APIClient()
    client.force_login(make_user(can_confirm=False))
    response = post_code(client, order, code)
    assert response.status_code == 403
    order.refresh_from_db()
    assert order.fulfilment == "out_for_delivery"
    assert DeliveryCode.objects.get(order_id=order.pk).failed_attempts == 0


def test_nobody_signed_in_is_refused(order, code):
    response = post_code(APIClient(), order, code)
    assert response.status_code in (401, 403)
    order.refresh_from_db()
    assert order.fulfilment == "out_for_delivery"


def test_a_wrong_code_gets_400_and_the_lockout_gets_429(order, code):
    client = APIClient()
    client.force_login(make_user(can_confirm=True))
    assert post_code(client, order, wrong_for(code)).status_code == 400
    for _ in range(4):
        post_code(client, order, wrong_for(code))
    assert post_code(client, order, code).status_code == 429


def test_an_unknown_reference_gets_404(db):
    client = APIClient()
    client.force_login(make_user(can_confirm=True))
    response = client.post(
        reverse("orders-delivery-confirm", kwargs={"reference": "SKNOSUCHREF"}),
        {"code": "123456"},
        format="json",
        HTTP_ORIGIN=ORIGIN,
    )
    assert response.status_code == 404


def test_a_request_with_no_code_gets_400(order, code):
    client = APIClient()
    client.force_login(make_user(can_confirm=True))
    response = client.post(
        reverse("orders-delivery-confirm", kwargs={"reference": order.reference}),
        {},
        format="json",
        HTTP_ORIGIN=ORIGIN,
    )
    assert response.status_code == 400


# --- two riders at once --------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_two_riders_submitting_the_right_code_deliver_the_order_once():
    placed = make_order()
    code = codes.issue_delivery_code(placed.pk, actor="system:test")

    def submit(actor):
        try:
            return services.confirm_delivery(placed.reference, code, actor=actor).status
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, ["user:1", "user:2"]))
    assert sorted(results) == [services.ALREADY_DELIVERED, services.DELIVERED_OK]
    assert Order.objects.get(pk=placed.pk).events.filter(event="delivered").count() == 1
