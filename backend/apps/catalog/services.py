"""Catalog services. Other apps call these, never the catalog models directly."""

from collections.abc import Sequence
from dataclasses import dataclass

from apps.pricing.money import Money
from apps.pricing.services import PricedLine, PriceLineInput, resolve_price

from .models import Variant


class CatalogError(ValueError):
    """A requested variant cannot be sold."""

    def __init__(self, message: str, variant_id: int | None = None) -> None:
        super().__init__(message)
        self.variant_id = variant_id


@dataclass(frozen=True)
class CartItem:
    variant_id: int
    quantity: int


def price_cart(items: Sequence[CartItem]) -> list[PricedLine]:
    """Look the variants up and price them with resolve_price().

    The caller supplies only variant ids and quantities. Prices always come from the database.
    Two queries however many items there are.
    """
    if not items:
        return []
    wanted = {item.variant_id for item in items}
    variants = {
        variant.id: variant
        for variant in Variant.objects.filter(
            id__in=wanted, is_active=True, product__is_active=True
        ).prefetch_related("tiers")
    }
    lines = []
    for item in items:
        variant = variants.get(item.variant_id)
        if variant is None:
            raise CatalogError(f"variant {item.variant_id} is not available", item.variant_id)
        tiers = {tier.tier: Money(tier.price_pesewas) for tier in variant.tiers.all()}
        lines.append(
            PriceLineInput(
                product_id=variant.product_id,
                variant_id=variant.id,
                quantity=item.quantity,
                tiers=tiers,
            )
        )
    return resolve_price(lines)
