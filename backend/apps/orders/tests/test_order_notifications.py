import pytest

from apps.delivery.fees import DOORSTEP, STATION
from apps.messaging.models import OutboxMessage
from apps.orders import checkout, notifications, settlement

PHONE = "+233201234567"  # a made-up number
PAID = (
    "S.K Clothing: we received your payment for order {reference} (GHS {total}). "
    "We will text you when it is on its way."
)
COD = (
    "S.K Clothing: we received order {reference} (GHS {total}). "
    "We will call you to confirm it before we pack it."
)


def place_online(shop, key="notify-key-0001"):
    request = checkout.CheckoutRequest(
        items=((shop.shirt, 1),),
        delivery_method=STATION,
        contact_name="Test Customer",
        contact_phone=PHONE,
        station_name="Kumasi STC",
    )
    return checkout.checkout(request, idempotency_key=key, user_id=None).order


def place_cod(shop, key="notify-key-0002"):
    request = checkout.CheckoutRequest(
        items=((shop.shirt, 1),),
        delivery_method=DOORSTEP,
        contact_name="Test Customer",
        contact_phone=PHONE,
        pay_on_delivery=True,
        latitude=5.61,
        longitude=-0.19,
        address="12 Test Street",
    )
    return checkout.checkout(request, idempotency_key=key, user_id=None).order


def test_amounts_are_shown_in_cedis_without_floating_point():
    assert [notifications._ghs(n) for n in (0, 5, 100, 7500, 12345)] == [
        "0.00",
        "0.05",
        "1.00",
        "75.00",
        "123.45",
    ]


def test_an_online_order_gets_no_message_until_it_is_paid(shop):
    place_online(shop)
    assert OutboxMessage.objects.count() == 0


def test_a_verified_payment_queues_the_approved_message(shop):
    order = place_online(shop)  # 5000 for the shirt plus 2500 for the station
    assert settlement.settle_payment(order.pk, order.total_pesewas) == settlement.PAID
    message = OutboxMessage.objects.get()
    assert message.template == "payment_received" and message.recipient == PHONE
    assert message.body == PAID.format(reference=order.reference, total="75.00")


def test_a_second_payment_notice_sends_nothing_new(shop):
    order = place_online(shop)
    settlement.settle_payment(order.pk, order.total_pesewas)
    assert settlement.settle_payment(order.pk, order.total_pesewas) == settlement.ALREADY_PAID
    assert OutboxMessage.objects.count() == 1


def test_a_payment_of_the_wrong_amount_sends_nothing(shop):
    order = place_online(shop)
    with pytest.raises(settlement.AmountMismatch):
        settlement.settle_payment(order.pk, order.total_pesewas - 1)
    assert OutboxMessage.objects.count() == 0


def test_a_pay_on_delivery_order_queues_the_approved_message_at_checkout(shop):
    order = place_cod(shop)
    message = OutboxMessage.objects.get()
    total = notifications._ghs(order.total_pesewas)
    assert message.template == "order_received_cod" and message.recipient == PHONE
    assert message.body == COD.format(reference=order.reference, total=total)


def test_repeating_a_pay_on_delivery_checkout_sends_one_message(shop):
    place_cod(shop)
    place_cod(shop)  # the same idempotency key: the same order comes back
    assert OutboxMessage.objects.count() == 1
