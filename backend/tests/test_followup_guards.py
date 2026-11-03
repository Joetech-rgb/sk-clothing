"""Tests for the guards added to make the type check pass (PROGRESS.md, deviations awaiting
approval). Each one documents a behaviour that must not silently change."""

import pytest

from apps.delivery.fees import PICKUP, DeliveryQuote
from apps.identity.models import User
from apps.orders import checkout, settlement
from apps.orders.models import Order
from apps.orders.services import LineInput, create_order

PHONE = "+233201234567"  # a made-up number


def awaiting_quote_order():
    line = LineInput(
        variant_id=1,
        name="Test shirt",
        quantity=1,
        tier="retail",
        unit_price_pesewas=1000,
        list_price_pesewas=1000,
        tier_price_pesewas=1000,
        source="tier",
    )
    order, _ = create_order(
        idempotency_key="followup-key-0001",
        lines=[line],
        delivery_method="doorstep",
        delivery_fee_pesewas=None,
        awaiting_quote=True,
        contact_phone=PHONE,
    )
    return order


def test_get_by_natural_key_with_no_username_raises_does_not_exist():
    with pytest.raises(User.DoesNotExist):
        User.objects.get_by_natural_key(None)


@pytest.mark.django_db
def test_an_order_with_no_total_cannot_be_paid():
    order = awaiting_quote_order()
    assert order.total_pesewas is None
    with pytest.raises(settlement.NotPayable) as info:
        settlement.payable_order(order.reference)
    assert info.value.why == "awaiting_quote"


@pytest.mark.django_db
@pytest.mark.parametrize("paid", [0, 1000])
def test_a_payment_for_an_order_with_no_total_is_refused_and_changes_nothing(paid):
    order = awaiting_quote_order()
    with pytest.raises(settlement.AmountMismatch):
        settlement.settle_payment(order.pk, paid)
    order.refresh_from_db()
    assert (order.payment, order.fulfilment) == ("pending", "awaiting_quote")
    assert order.events.count() == 1  # only the creation event


@pytest.mark.django_db
def test_checkout_stops_on_a_priced_quote_that_has_no_fee(monkeypatch):
    monkeypatch.setattr(checkout, "price_cart", lambda items: [])
    monkeypatch.setattr(checkout, "variant_labels", lambda ids: {})
    monkeypatch.setattr(
        checkout.delivery,
        "get_quote",
        lambda method, **kwargs: DeliveryQuote(PICKUP, "priced", None, False),
    )
    request = checkout.CheckoutRequest(
        items=((1, 1),),
        delivery_method=PICKUP,
        contact_name="Test Customer",
        contact_phone=PHONE,
    )
    with pytest.raises(AssertionError):
        checkout.checkout(request, idempotency_key="followup-key-0002", user_id=None)
    assert Order.objects.count() == 0  # nothing was created
