"""Shapes shared by several apps' API responses. Pure Python."""

from typing import Any

from apps.pricing.money import Money


def money_json(money: Money) -> dict[str, Any]:
    """Whole pesewas plus a ready-made display string. The browser only ever shows prices."""
    return {"pesewas": money.pesewas, "display": str(money)}
