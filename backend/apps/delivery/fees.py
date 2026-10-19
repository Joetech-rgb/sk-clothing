"""Delivery fees. Pure Python: no database, no clock.

Rules from the brief (CLAUDE.md section 5):
- Pickup is free.
- Station delivery uses the admin-managed station table. A station that is not in the table puts
  the order in "awaiting quote" until staff set a fee.
- Doorstep fee = max(minimum_fee, base_fee + rate_per_km x km), where km is the straight-line
  distance from the shop times a road factor (1.3). Beyond the maximum distance the order goes to
  "awaiting quote". Every value is an admin setting, none is hard-coded here.
- Pay on delivery is offered only for Accra doorstep orders.

Interpretations (ADR 0010, to confirm): "Accra doorstep" means a doorstep order that could be
priced, i.e. inside the maximum distance. The maximum distance is compared with the road-adjusted
km, the same km the fee uses. The fee is rounded half up to a whole pesewa.

Floats are used only for map geometry. Money is whole pesewas and the fee is computed with Decimal.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from math import asin, cos, isfinite, radians, sin, sqrt

from apps.pricing.money import Money

PICKUP = "pickup"
STATION = "station"
DOORSTEP = "doorstep"
METHODS = frozenset({PICKUP, STATION, DOORSTEP})

PRICED = "priced"
AWAITING_QUOTE = "awaiting_quote"

EARTH_RADIUS_KM = 6371.0088
KM_PLACES = Decimal("0.001")


@dataclass(frozen=True)
class GeoPoint:
    lat: float
    lng: float

    def __post_init__(self) -> None:
        for value in (self.lat, self.lng):
            if isinstance(value, bool) or not isinstance(value, int | float) or not isfinite(value):
                raise ValueError("coordinates must be finite numbers")
        if not -90 <= self.lat <= 90 or not -180 <= self.lng <= 180:
            raise ValueError("coordinates are out of range")


@dataclass(frozen=True)
class DoorstepSettings:
    shop: GeoPoint
    minimum_fee: Money
    base_fee: Money
    rate_per_km: Money  # pesewas for each road km
    max_distance_km: Decimal
    road_factor: Decimal = Decimal("1.3")

    def __post_init__(self) -> None:
        for money in (self.minimum_fee, self.base_fee, self.rate_per_km):
            if money.pesewas < 0:
                raise ValueError("fees cannot be negative")
        if self.max_distance_km <= 0:
            raise ValueError("max_distance_km must be above zero")
        if self.road_factor <= 0:
            raise ValueError("road_factor must be above zero")


@dataclass(frozen=True)
class DeliveryQuote:
    method: str
    status: str  # PRICED or AWAITING_QUOTE
    fee: Money | None  # None while awaiting a quote
    cod_allowed: bool
    reason: str | None = None  # why it is awaiting a quote
    road_km: Decimal | None = None  # doorstep only


def straight_line_km(a: GeoPoint, b: GeoPoint) -> float:
    """Great-circle distance (haversine)."""
    lat1, lat2 = radians(a.lat), radians(b.lat)
    d_lat, d_lng = lat2 - lat1, radians(b.lng - a.lng)
    h = sin(d_lat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(d_lng / 2) ** 2
    return 2 * EARTH_RADIUS_KM * asin(min(1.0, sqrt(h)))


def doorstep_quote_for_distance(straight_km: Decimal, settings: DoorstepSettings) -> DeliveryQuote:
    """The doorstep quote for a known straight-line distance."""
    if straight_km < 0:
        raise ValueError("distance cannot be negative")
    road_km = (straight_km * settings.road_factor).quantize(KM_PLACES, ROUND_HALF_UP)
    if road_km > settings.max_distance_km:
        return DeliveryQuote(
            DOORSTEP, AWAITING_QUOTE, None, False, reason="beyond_max_distance", road_km=road_km
        )
    raw = Decimal(settings.base_fee.pesewas) + Decimal(settings.rate_per_km.pesewas) * road_km
    fee = max(Decimal(settings.minimum_fee.pesewas), raw).quantize(Decimal("1"), ROUND_HALF_UP)
    return DeliveryQuote(DOORSTEP, PRICED, Money(int(fee)), True, road_km=road_km)


def normalise_station_name(name: str) -> str:
    return " ".join(name.casefold().split())


def station_fee(name: str, stations: Mapping[str, Money]) -> Money | None:
    """The fee for a station name, ignoring case and spacing. None if it is not listed."""
    wanted = normalise_station_name(name)
    for listed, fee in stations.items():
        if normalise_station_name(listed) == wanted:
            return fee
    return None


def quote_delivery(
    method: str,
    *,
    station_name: str | None = None,
    stations: Mapping[str, Money] | None = None,
    destination: GeoPoint | None = None,
    doorstep: DoorstepSettings | None = None,
) -> DeliveryQuote:
    if method not in METHODS:
        raise ValueError(f"unknown delivery method {method!r}")
    if method == PICKUP:
        return DeliveryQuote(PICKUP, PRICED, Money(0), False)
    if method == STATION:
        if not station_name or not station_name.strip():
            raise ValueError("a station name is required")
        fee = station_fee(station_name, stations or {})
        if fee is None:
            return DeliveryQuote(STATION, AWAITING_QUOTE, None, False, reason="unlisted_station")
        return DeliveryQuote(STATION, PRICED, fee, False)
    if destination is None or doorstep is None:
        raise ValueError("a destination and doorstep settings are required")
    km = Decimal(repr(straight_line_km(doorstep.shop, destination)))
    return doorstep_quote_for_distance(km, doorstep)
