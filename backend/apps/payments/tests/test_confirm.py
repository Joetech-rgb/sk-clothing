import logging

import pytest

from apps.inventory import services as inventory
from apps.inventory.models import Reservation, StockMovement
from apps.orders import services as order_services
from apps.orders.models import OrderEvent, OrderReservation
from apps.orders.states import Event
from apps.payments.client import PaystackError
from apps.payments.models import PaymentAttempt
from apps.payments.tests.helpers import (
    EMAIL,
    attempts,
    expire_holds,
    fake,
    holds_status,
    level,
    order_row,
    place_order,
    start_ok,
    verify_page,
    webhook,
)

pytestmark = pytest.mark.django_db


def events(order_reference):
    return list(order_row(order_reference).events.values_list("event", flat=True))


def sales(variant_id):
    return StockMovement.objects.filter(variant_id=variant_id, kind="sale").count()


def setup_payment(shop, items=None, **kwargs):
    order = place_order(items or [(shop.shirt, 2)], **kwargs)
    return order, start_ok(order["reference"])


# --- paying, once -----------------------------------------------------------------------------


def test_a_verified_payment_marks_the_order_paid_and_sells_the_stock(shop):
    order, reference = setup_payment(shop, [(shop.shirt, 2), (shop.shoe, 1)])
    response = verify_page(reference)
    assert response.status_code == 200
    assert response.json() == {
        "outcome": "paid",
        "order_reference": order["reference"],
        "payment_status": "paid",
        "fulfilment_status": "to_pack",
        "refund_status": "none",
    }
    row = order_row(order["reference"])
    assert (row.payment, row.fulfilment, row.refund) == ("paid", "to_pack", "none")
    assert (level(shop.shirt).on_hand, level(shop.shirt).reserved) == (8, 0)
    assert (level(shop.shoe).on_hand, level(shop.shoe).reserved) == (3, 0)
    assert holds_status(order["reference"]) == ["confirmed", "confirmed"]
    assert sales(shop.shirt) == 1 and sales(shop.shoe) == 1
    assert events(order["reference"]) == ["created", "payment_confirmed"]
    (attempt,) = attempts(order["reference"])
    assert attempt.status == "success" and attempt.confirmed_at is not None
    assert inventory.verify_ledger(shop.shirt) == [] and inventory.verify_ledger(shop.shoe) == []


def test_the_webhook_also_marks_the_order_paid(shop):
    order, reference = setup_payment(shop)
    assert webhook(reference).status_code == 200
    assert order_row(order["reference"]).payment == "paid"
    assert level(shop.shirt).on_hand == 8


def test_a_payment_is_applied_exactly_once_however_often_it_is_reported(shop):
    order, reference = setup_payment(shop)
    for _ in range(3):
        assert webhook(reference).status_code == 200
    for _ in range(2):
        response = verify_page(reference)
        assert response.status_code == 200 and response.json()["payment_status"] == "paid"
    assert level(shop.shirt).on_hand == 8 and sales(shop.shirt) == 1
    assert events(order["reference"]) == ["created", "payment_confirmed"]
    assert fake().verify_calls == [reference]  # a payment already applied is not asked about again
    assert inventory.verify_ledger(shop.shirt) == []


@pytest.mark.parametrize("first", ["webhook", "page"])
def test_the_webhook_and_the_return_page_may_arrive_in_either_order(shop, first):
    order, reference = setup_payment(shop)
    steps = [lambda: webhook(reference), lambda: verify_page(reference)]
    for step in steps if first == "webhook" else reversed(steps):
        assert step().status_code == 200
    assert order_row(order["reference"]).payment == "paid" and sales(shop.shirt) == 1


@pytest.mark.parametrize(
    ("method", "extra"),
    [
        ("pickup", None),
        ("station", {"station_name": "Kumasi STC"}),
        ("doorstep", {"latitude": 5.61, "longitude": -0.19, "address": "12 Oak Street"}),
    ],
)
def test_every_delivery_kind_is_paid_for_its_full_total(shop, method, extra):
    order, reference = setup_payment(shop, method=method, extra=extra)
    assert fake().initialized[reference]["amount"] == order["total"]["pesewas"]
    assert verify_page(reference).json()["outcome"] == "paid"


# --- never trusting what the customer or the webhook says -------------------------------------


def test_a_webhook_that_claims_success_is_not_believed_if_paystack_says_otherwise(shop):
    order, reference = setup_payment(shop)
    fake().set_outcome(reference, status="failed")
    assert webhook(reference, status="success").status_code == 200
    row = order_row(order["reference"])
    assert row.payment == "failed" and row.fulfilment == "pending"
    assert level(shop.shirt).on_hand == 10 and sales(shop.shirt) == 0
    assert attempts(order["reference"]).get().status == "failed"


def test_a_webhook_cannot_name_the_amount(shop):
    order, reference = setup_payment(shop)
    assert webhook(reference, amount=1).status_code == 200  # the body says 1 pesewa
    assert order_row(order["reference"]).payment == "paid"  # Paystack's own answer decides


def test_a_return_page_visit_proves_nothing_until_paystack_confirms(shop):
    order, reference = setup_payment(shop)
    fake().set_outcome(reference, status="abandoned")
    response = verify_page(reference)
    assert response.status_code == 200 and response.json()["outcome"] == "pending"
    assert order_row(order["reference"]).payment == "pending"
    assert attempts(order["reference"]).get().status == "pending"
    fake().set_outcome(reference, status="success")
    assert verify_page(reference).json()["outcome"] == "paid"


def test_a_forged_webhook_is_refused_and_paystack_is_not_even_asked(shop):
    order, reference = setup_payment(shop)
    assert webhook(reference, secret="the-wrong-secret").status_code == 401
    assert fake().verify_calls == [] and order_row(order["reference"]).payment == "pending"


def test_a_webhook_for_a_payment_we_never_started_is_ignored(shop):
    assert webhook("SOMEONE-ELSES-REF").status_code == 200
    assert fake().verify_calls == [] and PaymentAttempt.objects.count() == 0


def test_other_webhook_events_do_not_confirm_anything(shop):
    order, reference = setup_payment(shop)
    assert webhook(reference, event="charge.failed").status_code == 200
    assert fake().verify_calls == [] and order_row(order["reference"]).payment == "pending"


@pytest.mark.parametrize(
    ("amount", "currency"),
    [(1, "GHS"), (None, "GHS"), (10_000_000, "GHS"), (10000, "NGN"), (10000, "")],
)
def test_a_wrong_amount_or_currency_is_never_applied(shop, caplog, amount, currency):
    caplog.set_level(logging.ERROR)
    order, reference = setup_payment(shop, [(shop.shirt, 2)])
    from apps.payments.client import VerifyResult

    fake().outcomes[reference] = VerifyResult("success", amount, currency, reference)
    assert webhook(reference).status_code == 200  # answered, so Paystack stops retrying
    row = order_row(order["reference"])
    assert row.payment == "pending" and row.fulfilment == "pending"
    assert level(shop.shirt).on_hand == 10 and sales(shop.shirt) == 0
    assert attempts(order["reference"]).get().status == "mismatch"
    assert any("needs a person" in r.getMessage() for r in caplog.records)


def test_a_reference_paystack_reports_differently_is_not_applied(shop):
    order, reference = setup_payment(shop)
    from apps.payments.client import VerifyResult

    fake().outcomes[reference] = VerifyResult("success", 10000, "GHS", "SK-SOMETHING-ELSE")
    verify_page(reference)
    assert order_row(order["reference"]).payment == "pending"
    assert attempts(order["reference"]).get().status == "mismatch"


# --- Paystack unreachable ---------------------------------------------------------------------


def test_when_paystack_cannot_be_reached_the_webhook_asks_to_be_sent_again_and_the_repeat_works(
    shop,
):
    order, reference = setup_payment(shop)
    fake().fail_verify(reference, PaystackError("down", retryable=True))
    assert webhook(reference).status_code == 503
    assert order_row(order["reference"]).payment == "pending"
    assert attempts(order["reference"]).get().status == "pending"
    del fake().outcomes[reference]  # Paystack is back
    repeat = webhook(reference)  # the same event again: it is already recorded as seen
    assert repeat.status_code == 200 and repeat.json()["status"] == "duplicate"
    assert order_row(order["reference"]).payment == "paid" and level(shop.shirt).on_hand == 8


def test_the_return_page_says_so_when_paystack_cannot_be_reached(shop):
    order, reference = setup_payment(shop)
    fake().fail_verify(reference, PaystackError("down", retryable=True))
    response = verify_page(reference)
    assert response.status_code == 503
    assert response.json()["error"]["details"]["reason"] == "payment_unavailable"
    assert order_row(order["reference"]).payment == "pending"


def test_the_return_page_does_not_know_payments_we_never_started(shop):
    response = verify_page("SK-NOT-OURS")
    assert response.status_code == 404
    assert response.json()["error"]["details"]["reason"] == "unknown_reference"
    assert verify_page("").status_code == 404


# --- a failed attempt, then a good one --------------------------------------------------------


def test_a_failed_attempt_leaves_the_stock_held_and_a_second_attempt_can_succeed(shop):
    order, first = setup_payment(shop)
    fake().set_outcome(first, status="failed")
    assert verify_page(first).json()["payment_status"] == "failed"
    assert level(shop.shirt).reserved == 2  # still held for the customer's next try
    second = start_ok(order["reference"])
    assert verify_page(second).json()["outcome"] == "paid"
    assert order_row(order["reference"]).payment == "paid" and level(shop.shirt).on_hand == 8


def test_a_failed_attempt_cannot_undo_a_payment_that_already_succeeded(shop):
    order, first = setup_payment(shop)
    second = start_ok(order["reference"])
    assert verify_page(first).json()["outcome"] == "paid"
    fake().set_outcome(second, status="failed")
    response = verify_page(second)
    assert response.json()["payment_status"] == "paid"
    assert order_row(order["reference"]).payment == "paid" and sales(shop.shirt) == 1


def test_paying_twice_is_flagged_for_a_refund_and_sells_once(shop, caplog):
    caplog.set_level(logging.ERROR)
    order, first = setup_payment(shop)
    second = start_ok(order["reference"])
    assert verify_page(first).json()["outcome"] == "paid"
    assert verify_page(second).json()["outcome"] == "duplicate"
    statuses = sorted(a.status for a in attempts(order["reference"]))
    assert statuses == ["duplicate", "success"]
    assert level(shop.shirt).on_hand == 8 and sales(shop.shirt) == 1
    assert any("needs a refund" in r.getMessage() for r in caplog.records)
    assert verify_page(second).json()["outcome"] == "already_confirmed"


# --- paying after the hold ran out (ADR 0008) -------------------------------------------------


def test_paying_late_with_stock_still_available_takes_it_again_and_sells_it(shop):
    order, reference = setup_payment(shop)
    assert expire_holds(order["reference"]) == 1
    assert level(shop.shirt).reserved == 0 and level(shop.shirt).on_hand == 10
    assert verify_page(reference).json()["outcome"] == "paid"
    row = order_row(order["reference"])
    assert (row.payment, row.fulfilment, row.refund) == ("paid", "to_pack", "none")
    assert (level(shop.shirt).on_hand, level(shop.shirt).reserved) == (8, 0)
    assert sales(shop.shirt) == 1
    assert OrderReservation.objects.filter(order=row).count() == 2  # the old hold and the new one
    assert inventory.verify_ledger(shop.shirt) == []


def test_paying_late_when_someone_else_took_the_last_unit_oversells_nothing(shop):
    order, reference = setup_payment(shop, [(shop.scarce, 1)])
    expire_holds(order["reference"])
    other = place_order([(shop.scarce, 1)], phone="0249999999")  # takes the freed unit
    assert verify_page(reference).json()["outcome"] == "paid_not_fulfillable"
    row = order_row(order["reference"])
    assert (row.payment, row.fulfilment, row.refund) == ("paid", "not_fulfillable", "requested")
    assert (level(shop.scarce).on_hand, level(shop.scarce).reserved) == (1, 1)  # the other buyer's
    assert sales(shop.scarce) == 0
    assert order_row(other["reference"]).payment == "pending"
    assert attempts(order["reference"]).get().status == "success"
    assert events(order["reference"]) == [
        "created",
        "payment_confirmed",
        "stock_unavailable",
    ]
    assert inventory.verify_ledger(shop.scarce) == []


def test_late_payment_is_all_or_nothing_across_items(shop):
    order, reference = setup_payment(shop, [(shop.shirt, 2), (shop.scarce, 1)])
    expire_holds(order["reference"])
    place_order([(shop.scarce, 1)], phone="0249999999")
    assert verify_page(reference).json()["outcome"] == "paid_not_fulfillable"
    assert order_row(order["reference"]).fulfilment == "not_fulfillable"
    assert (level(shop.shirt).on_hand, level(shop.shirt).reserved) == (10, 0)  # nothing was sold
    assert sales(shop.shirt) == 0 and holds_status(order["reference"]) == ["expired", "expired"]
    assert inventory.verify_ledger(shop.shirt) == []


def test_when_only_part_of_the_hold_ran_out_nothing_is_counted_twice(shop):
    order, reference = setup_payment(shop, [(shop.shirt, 2), (shop.shoe, 1)])
    row = order_row(order["reference"])
    shirt_hold = row.reservations.get(variant_id=shop.shirt).reservation_id
    inventory._release([shirt_hold], "expired")  # only the shirt hold runs out
    assert verify_page(reference).json()["outcome"] == "paid"
    for variant in (shop.shirt, shop.shoe):
        assert level(variant).reserved == 0 and sales(variant) == 1, variant
    assert (level(shop.shirt).on_hand, level(shop.shoe).on_hand) == (8, 3)
    assert not Reservation.objects.filter(status="active").exists()
    assert inventory.verify_ledger(shop.shirt) == [] and inventory.verify_ledger(shop.shoe) == []


def test_paying_for_an_order_that_was_cancelled_keeps_it_cancelled_and_asks_for_a_refund(shop):
    order, reference = setup_payment(shop)
    order_services.transition(order_row(order["reference"]).pk, Event.CANCEL, actor="test")
    assert verify_page(reference).json()["outcome"] == "paid_order_closed"
    row = order_row(order["reference"])
    assert (row.payment, row.fulfilment, row.refund) == ("paid", "cancelled", "requested")
    assert sales(shop.shirt) == 0


def test_a_stock_unavailable_order_that_is_paid_late_asks_for_a_refund(shop):
    order, reference = setup_payment(shop)
    order_services.transition(order_row(order["reference"]).pk, Event.STOCK_UNAVAILABLE, actor="t")
    assert verify_page(reference).json()["outcome"] == "paid_order_closed"
    assert order_row(order["reference"]).refund == "requested"


# --- privacy ----------------------------------------------------------------------------------


def test_emails_phone_numbers_and_names_never_reach_the_logs(shop, caplog):
    caplog.set_level(logging.DEBUG)
    order = place_order([(shop.shirt, 1)])
    reference = start_ok(order["reference"], "secret.person@example.com")
    webhook(reference)
    verify_page(reference)
    text = "\n".join(f"{r.getMessage()} {r.args}" for r in caplog.records)
    for secret in ("secret.person", "0241234567", "241234567", "Ama Mensah"):
        assert secret not in text


def test_the_return_page_shows_statuses_only(shop):
    order, reference = setup_payment(shop)
    text = verify_page(reference).content.decode()
    for secret in (
        EMAIL,
        "0241234567",
        "Ama Mensah",
        "amount",
        "pesewas",
        str(order_row(order["reference"]).pk),
    ):
        assert secret not in text


def test_a_payment_adds_to_the_order_history_once_with_a_named_actor(shop):
    order, reference = setup_payment(shop)
    verify_page(reference)
    verify_page(reference)
    paid = OrderEvent.objects.get(order__reference=order["reference"], event="payment_confirmed")
    assert paid.actor == "system:payment"
    assert paid.before["payment"] == "pending" and paid.after["payment"] == "paid"


def test_the_order_side_refuses_a_wrong_amount_on_its_own(shop):
    from apps.orders import settlement

    order, _ = setup_payment(shop)
    row = order_row(order["reference"])
    for wrong in (1, row.total_pesewas - 1, row.total_pesewas + 1):
        with pytest.raises(settlement.AmountMismatch):
            settlement.settle_payment(row.pk, wrong)
    assert order_row(order["reference"]).payment == "pending" and level(shop.shirt).on_hand == 10


def test_return_page_checks_per_address_are_limited(shop, settings):
    settings.PAYMENT_LIMITS = {"start_ip_rate": "10000/hour", "verify_ip_rate": "2/hour"}
    order, reference = setup_payment(shop)
    fake().set_outcome(reference, status="pending")
    codes = [verify_page(reference).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
    assert len(fake().verify_calls) == 2  # the refused request never reached Paystack
