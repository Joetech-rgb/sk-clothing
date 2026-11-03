"""Cancelling orders that were never paid for, and giving their stock back.

An unpaid order is NOT cancelled when its 15-minute stock hold runs out. ADR 0008 says a payment
that arrives after the hold must try to take the stock again, and refund only if it is gone, so the
order has to stay payable for a while. It is cancelled after a longer grace period:

- online orders nobody has paid for (pending or failed payment): 24 hours;
- orders waiting for a staff quote: 72 hours;
- pay-on-delivery orders staff have not confirmed by phone: 72 hours.

A cancelled unpaid order has its payment voided, no refund (no money was taken), and any hold
still in place is released. If a payment arrives afterwards, the order stays cancelled and a refund
is requested (see settlement.py). Payment and cancellation both lock the order row, so exactly one
of them gets there first.

The limits can be overridden with an ORDER_EXPIRY_HOURS setting.
"""

import logging
from datetime import datetime, timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.inventory import services as inventory

from .models import Order
from .services import transition
from .states import Event, Fulfilment, Payment

logger = logging.getLogger(__name__)

DEFAULT_HOURS: dict[str, int] = {
    "unpaid_online": 24,
    "awaiting_quote": 72,
    "cod_unconfirmed": 72,
}


def hours(name: str) -> timedelta:
    return timedelta(
        hours=getattr(settings, "ORDER_EXPIRY_HOURS", {}).get(name, DEFAULT_HOURS[name])
    )


def _stale_filter(now: datetime) -> Q:
    return (
        Q(
            payment__in=[Payment.PENDING.value, Payment.FAILED.value],
            fulfilment=Fulfilment.PENDING.value,
            created_at__lt=now - hours("unpaid_online"),
        )
        | Q(
            payment=Payment.PENDING.value,
            fulfilment=Fulfilment.AWAITING_QUOTE.value,
            created_at__lt=now - hours("awaiting_quote"),
        )
        | Q(
            payment=Payment.COD_PENDING.value,
            fulfilment=Fulfilment.PENDING.value,
            created_at__lt=now - hours("cod_unconfirmed"),
        )
    )


def cancel_if_stale(order_id: int, now: datetime) -> bool:
    """Cancel one order if it is still unpaid and past its grace period. False if not."""
    with transaction.atomic():
        order = Order.objects.select_for_update().filter(_stale_filter(now), pk=order_id).first()
        if order is None:  # paid, confirmed or cancelled in the meantime, or not old enough
            return False
        transition(order.pk, Event.CANCEL, actor="system:expiry")
        inventory.release([hold.reservation_id for hold in order.reservations.all()])
    return True


def cancel_stale_orders(*, now: datetime | None = None, batch_size: int = 200) -> int:
    """Cancel every stale unpaid order, a batch at a time. Returns how many were cancelled."""
    now = now or timezone.now()
    cancelled = 0
    while True:
        ids = list(
            Order.objects.filter(_stale_filter(now))
            .order_by("id")
            .values_list("pk", flat=True)[:batch_size]
        )
        done = sum(cancel_if_stale(order_id, now) for order_id in ids)
        cancelled += done
        if done == 0:  # nothing left, or the rest changed under us: the next run will see them
            break
    if cancelled:
        logger.info("cancelled %s unpaid orders", cancelled)
    return cancelled
