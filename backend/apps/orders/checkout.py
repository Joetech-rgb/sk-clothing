"""Checkout: price the basket, quote delivery, hold the stock and freeze the order, in one
transaction. The browser sends only variant ids, quantities and where to deliver; every price and
fee comes from the server.

Guarantees, and what enforces each:
- Retrying is safe: the same Idempotency-Key and the same request returns the same order and holds
  stock once. The same key with a different request is refused. The key is scoped to the signed-in
  customer (or to guests), so nobody can fetch another customer's order by guessing a key.
- Stock is held for every item or none, and a failure after the hold undoes the hold: the hold and
  the order are written in one transaction.
- The last unit goes to one buyer: inventory locks stock rows in a fixed order.
- One phone number cannot tie up stock with a pile of unpaid orders: a per-number limit, checked
  under a per-number lock so simultaneous requests cannot slip past it.

Never log a phone number, a name or an address.
"""

import hashlib
import json
import logging
from dataclasses import dataclass

from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone

from apps.catalog.services import CartItem, CatalogError, price_cart, variant_labels
from apps.delivery import services as delivery
from apps.delivery.fees import AWAITING_QUOTE, DOORSTEP, PICKUP, STATION, normalise_station_name
from apps.inventory import services as inventory
from apps.inventory.errors import IdempotencyConflict, InsufficientStock
from apps.pricing.services import PricingError

from .models import Order, OrderReservation
from .services import LineInput, create_order
from .states import Fulfilment, Payment

logger = logging.getLogger(__name__)

DEFAULT_LIMITS: dict[str, int | str] = {
    "open_orders_per_phone": 3,  # unpaid orders from one number inside the hold window
    "checkout_ip_rate": "30/hour",  # checkouts per caller address
}
HOLD_WINDOW = inventory.RESERVATION_TTL


def limit(name: str) -> int | str:
    return getattr(settings, "CHECKOUT_LIMITS", {}).get(name, DEFAULT_LIMITS[name])


class CheckoutError(Exception):
    """Base class for refusals the customer can understand."""


class VariantUnavailable(CheckoutError):
    def __init__(self, variant_id: int | None) -> None:
        super().__init__("an item is not available")
        self.variant_id = variant_id


class OutOfStock(CheckoutError):
    def __init__(self, variant_id: int | None, available: int) -> None:
        super().__init__("not enough stock")
        self.variant_id = variant_id
        self.available = available


class CodNotAvailable(CheckoutError):
    pass


class BadDelivery(CheckoutError):
    pass


class IdempotencyMismatch(CheckoutError):
    pass


class TooManyOpenOrders(CheckoutError):
    pass


@dataclass(frozen=True)
class CheckoutRequest:
    items: tuple[tuple[int, int], ...]  # (variant_id, quantity), each variant once, sorted
    delivery_method: str
    contact_name: str
    contact_phone: str  # E.164
    pay_on_delivery: bool = False
    station_name: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    address: str = ""


@dataclass(frozen=True)
class CheckoutResult:
    order: Order
    created: bool
    reservation_expires_at: object  # a datetime, or None when nothing is held


def merge_items(pairs: list[tuple[int, int]]) -> tuple[tuple[int, int], ...]:
    """Add up repeated variants, so inventory sees each one once."""
    merged: dict[int, int] = {}
    for variant_id, quantity in pairs:
        merged[variant_id] = merged.get(variant_id, 0) + quantity
    return tuple(sorted(merged.items()))


def fingerprint(request: CheckoutRequest) -> str:
    """A hash of what the customer asked for, to tell a retry from a different request."""
    body = {
        "items": request.items,
        "method": request.delivery_method,
        "name": request.contact_name.strip(),
        "phone": request.contact_phone,
        "cod": request.pay_on_delivery,
        "station": normalise_station_name(request.station_name or ""),
        "lat": request.latitude,
        "lng": request.longitude,
        "address": " ".join(request.address.split()),
    }
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()


def stored_key(user_id: int | None, key: str) -> str:
    """The idempotency key as stored: scoped to the customer and hashed, so a raw key is never
    kept and one customer's key cannot collide with another's."""
    scope = f"user:{user_id}" if user_id else "guest"
    return hashlib.sha256(f"{scope}:{key}".encode()).hexdigest()[:48]


def _lock_phone(phone: str) -> None:
    """Make checkouts from one number take turns until the transaction ends."""
    if connection.vendor != "postgresql":
        return
    digest = hashlib.sha256(f"checkout:{phone}".encode()).digest()
    key = int.from_bytes(digest[:8], "big", signed=True)
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [key])


def _enforce_open_order_limit(phone: str) -> None:
    window_start = timezone.now() - HOLD_WINDOW
    open_orders = Order.objects.filter(
        contact_phone=phone,
        payment__in=[Payment.PENDING.value, Payment.COD_PENDING.value],
        fulfilment__in=[Fulfilment.PENDING.value, Fulfilment.AWAITING_QUOTE.value],
        created_at__gt=window_start,
    ).count()
    if open_orders >= int(limit("open_orders_per_phone")):
        raise TooManyOpenOrders


def _replay(order: Order, fp: str) -> CheckoutResult:
    if order.request_hash != fp:
        raise IdempotencyMismatch
    expiry = min(order.reservations.values_list("expires_at", flat=True), default=None)
    return CheckoutResult(order, created=False, reservation_expires_at=expiry)


def _line_inputs(priced, labels) -> list[LineInput]:
    return [
        LineInput(
            variant_id=line.variant_id,
            name=labels.get(line.variant_id, f"variant {line.variant_id}"),
            quantity=line.quantity,
            tier=line.tier,
            unit_price_pesewas=line.unit_price.pesewas,
            list_price_pesewas=line.list_price.pesewas,
            tier_price_pesewas=line.tier_price.pesewas,
            source=line.source,
            discounts=tuple(
                {
                    "discount_id": d.discount_id,
                    "kind": d.kind,
                    "value": str(d.value),
                    "unit_price_after_pesewas": d.unit_price_after.pesewas,
                }
                for d in line.discounts
            ),
        )
        for line in priced
    ]


def checkout(
    request: CheckoutRequest, *, idempotency_key: str, user_id: int | None
) -> CheckoutResult:
    """Place an order. Raises a CheckoutError subclass for anything the customer can fix."""
    key = stored_key(user_id, idempotency_key)
    fp = fingerprint(request)
    existing = Order.objects.filter(idempotency_key=key).first()
    if existing is not None:
        return _replay(existing, fp)

    try:
        priced = price_cart(
            [CartItem(variant_id, quantity) for variant_id, quantity in request.items]
        )
    except CatalogError as error:
        raise VariantUnavailable(error.variant_id) from error
    except PricingError as error:
        raise VariantUnavailable(None) from error
    try:
        quote = delivery.get_quote(
            request.delivery_method,
            station_name=request.station_name,
            latitude=request.latitude,
            longitude=request.longitude,
        )
    except ValueError as error:
        raise BadDelivery(str(error)) from error
    if request.pay_on_delivery and not quote.cod_allowed:
        raise CodNotAvailable
    awaiting = quote.status == AWAITING_QUOTE
    details: dict = {}
    if request.delivery_method == STATION:
        details = {"station_name": " ".join((request.station_name or "").split())}
    elif request.delivery_method == DOORSTEP:
        details = {
            "address": " ".join(request.address.split()),
            "latitude": request.latitude,
            "longitude": request.longitude,
        }
    if quote.reason:
        details["quote_reason"] = quote.reason
    if quote.road_km is not None:
        details["road_km"] = str(quote.road_km)
    lines = _line_inputs(priced, variant_labels([line.variant_id for line in priced]))

    try:
        with transaction.atomic():
            _lock_phone(request.contact_phone)
            existing = Order.objects.filter(idempotency_key=key).first()
            if existing is not None:  # an identical request finished while we waited
                return _replay(existing, fp)
            _enforce_open_order_limit(request.contact_phone)
            holds = inventory.reserve_many(
                [
                    inventory.StockRequest(variant_id, quantity)
                    for variant_id, quantity in request.items
                ],
                idempotency_key=key,
            )
            order, created = create_order(
                idempotency_key=key,
                lines=lines,
                delivery_method=request.delivery_method,
                delivery_fee_pesewas=None if awaiting else quote.fee.pesewas,
                cod=request.pay_on_delivery,
                awaiting_quote=awaiting,
                pickup=request.delivery_method == PICKUP,
                user_id=user_id,
                contact_phone=request.contact_phone,
                contact_name=request.contact_name.strip(),
                delivery_details=details,
                request_hash=fp,
                actor=f"user:{user_id}" if user_id else "guest",
            )
            if not created:  # another request with this key got in first
                return _replay(order, fp)  # raising here undoes any holds we just took
            OrderReservation.objects.bulk_create(
                OrderReservation(
                    order=order,
                    reservation_id=hold.pk,
                    variant_id=hold.variant_id,
                    quantity=hold.quantity,
                    expires_at=hold.expires_at,
                )
                for hold in holds
            )
    except InsufficientStock as error:
        raise OutOfStock(error.variant_id, error.available) from error
    except IdempotencyConflict as error:
        raise IdempotencyMismatch from error
    logger.info("order %s placed", order.reference)
    expiry = min(hold.expires_at for hold in holds)
    return CheckoutResult(order, created=True, reservation_expires_at=expiry)
