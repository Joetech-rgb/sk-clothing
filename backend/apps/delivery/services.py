"""Delivery services. Other apps call these, never the delivery models directly."""

import logging
from decimal import Decimal

from apps.pricing.money import Money

from .fees import (
    AWAITING_QUOTE,
    DOORSTEP,
    DeliveryQuote,
    DoorstepSettings,
    GeoPoint,
    quote_delivery,
)
from .models import DeliverySettings, Station

logger = logging.getLogger(__name__)


def load_doorstep_settings() -> DoorstepSettings | None:
    """The shop's settings, or None if staff have not filled them in (or they are unusable)."""
    row = DeliverySettings.objects.first()
    if row is None:
        return None
    try:
        return DoorstepSettings(
            shop=GeoPoint(float(row.shop_latitude), float(row.shop_longitude)),
            minimum_fee=Money(row.minimum_fee_pesewas),
            base_fee=Money(row.base_fee_pesewas),
            rate_per_km=Money(row.rate_per_km_pesewas),
            max_distance_km=Decimal(row.max_distance_km),
            road_factor=Decimal(row.road_factor),
        )
    except ValueError:
        logger.warning("delivery settings are not usable; doorstep orders will await a quote")
        return None


def station_fees() -> dict[str, Money]:
    return {s.name: Money(s.fee_pesewas) for s in Station.objects.filter(is_active=True)}


def get_quote(
    method: str,
    *,
    station_name: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
) -> DeliveryQuote:
    """Quote delivery for an order. Raises ValueError for input that cannot be quoted."""
    if method != DOORSTEP:
        return quote_delivery(method, station_name=station_name, stations=station_fees())
    if latitude is None or longitude is None:
        raise ValueError("a destination is required")
    destination = GeoPoint(latitude, longitude)
    settings = load_doorstep_settings()
    if settings is None:
        return DeliveryQuote(DOORSTEP, AWAITING_QUOTE, None, False, reason="not_configured")
    return quote_delivery(DOORSTEP, destination=destination, doorstep=settings)
