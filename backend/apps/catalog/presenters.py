"""Shapes sent to the storefront. Pure Python: no database, no Django.

Prices go out as whole pesewas plus a ready-made display string. The browser only ever shows
them; it never works one out.
"""

from collections.abc import Iterable, Mapping
from typing import Any

from apps.pricing.money import Money
from apps.pricing.services import TIER_THRESHOLDS


def money_json(money: Money) -> dict[str, Any]:
    return {"pesewas": money.pesewas, "display": str(money)}


def tier_rows(tiers: Mapping[str, Money]) -> list[dict[str, Any]]:
    """The price levels that are filled in, cheapest quantity first. Empty tiers are not shown."""
    return [
        {"tier": name, "min_quantity": threshold, "price": money_json(tiers[name])}
        for name, threshold in TIER_THRESHOLDS
        if name in tiers
    ]


def price_from(variant_tiers: Iterable[Mapping[str, Money]]) -> Money | None:
    """The lowest retail price across a product's variants, or None if none can be sold."""
    prices = [tiers["retail"] for tiers in variant_tiers if "retail" in tiers]
    return min(prices) if prices else None


def quantity_rules(variant_tiers: Iterable[Mapping[str, Money]]) -> list[dict[str, Any]]:
    """Which quantity thresholds exist anywhere on the product, so the page can say
    'buy 10 or more of any size or colour for the wholesale price'."""
    filled = {name for tiers in variant_tiers for name in tiers}
    return [
        {"tier": name, "min_quantity": threshold}
        for name, threshold in TIER_THRESHOLDS
        if name in filled and name != "retail"
    ]
