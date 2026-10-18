"""resolve_price(): the only place prices are computed.

Pure function: no database, no clock, no side effects. Callers (cart, checkout, POS,
reseller dashboard) build the inputs from the catalog and never accept a price from a client.

Rules (CLAUDE.md section 5):
- Tiers per variant: retail (1+), wholesale (10+), dealer (50+), bulk (200+).
- The threshold is checked against the quantity of the same PRODUCT summed across variants.
- Each variant is charged its own tier price.
- Only filled tiers exist. A missing tier is skipped.
- Among the tiers whose threshold is met, the lowest price wins.

Not built yet: discounts (waiting on how they are defined) and the reseller price (Phase 4).
"""

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .money import Money

# (tier name, minimum product quantity), lowest threshold first.
TIER_THRESHOLDS: tuple[tuple[str, int], ...] = (
    ("retail", 1),
    ("wholesale", 10),
    ("dealer", 50),
    ("bulk", 200),
)
TIER_NAMES = frozenset(name for name, _ in TIER_THRESHOLDS)


class PricingError(ValueError):
    """The inputs cannot be priced (bad quantity, missing retail price, negative price)."""


@dataclass(frozen=True)
class PriceLineInput:
    product_id: int
    variant_id: int
    quantity: int
    tiers: Mapping[str, Money]  # only the tiers that are filled in; "retail" is required


@dataclass(frozen=True)
class PricedLine:
    variant_id: int
    quantity: int
    tier: str
    unit_price: Money
    line_total: Money


def _validate(line: PriceLineInput) -> None:
    quantity = line.quantity
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 1:
        raise PricingError("quantity must be a whole number of at least 1")
    unknown = set(line.tiers) - TIER_NAMES
    if unknown:
        raise PricingError(f"unknown tier: {sorted(unknown)[0]}")
    if "retail" not in line.tiers:
        raise PricingError("every variant needs a retail price")
    for price in line.tiers.values():
        if not isinstance(price, Money) or price.pesewas < 0:
            raise PricingError("prices must be Money of zero or more")


def _price_line(line: PriceLineInput, product_quantity: int) -> PricedLine:
    best_name = "retail"
    best_price = line.tiers["retail"]
    for name, threshold in TIER_THRESHOLDS[1:]:
        price = line.tiers.get(name)
        # "<=": on a tie the higher tier is the one reported.
        if price is not None and product_quantity >= threshold and price <= best_price:
            best_name, best_price = name, price
    return PricedLine(
        variant_id=line.variant_id,
        quantity=line.quantity,
        tier=best_name,
        unit_price=best_price,
        line_total=best_price.times(line.quantity),
    )


def resolve_price(lines: Sequence[PriceLineInput]) -> list[PricedLine]:
    """Price every line. Output order matches input order."""
    for line in lines:
        _validate(line)
    product_quantity: dict[int, int] = defaultdict(int)
    for line in lines:
        product_quantity[line.product_id] += line.quantity
    return [_price_line(line, product_quantity[line.product_id]) for line in lines]
