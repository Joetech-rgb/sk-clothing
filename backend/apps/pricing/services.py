"""resolve_price(): the only place prices are computed.

Pure function: no database, no clock, no side effects. Callers (cart, checkout, POS,
reseller dashboard) build the inputs from the catalog and never accept a price from a client.

Rules (CLAUDE.md section 5, and ADR 0007):
- Tiers per variant: retail (1+), wholesale (10+), dealer (50+), bulk (200+).
- The threshold is checked against the quantity of the same PRODUCT summed across variants.
- Each variant is charged its own tier price. Only filled tiers exist.
- Among the tiers whose threshold is met, the lowest price wins.
- Discounts compete with that tier price: each eligible discount that is not stackable is worked
  out from the variant's retail price, and the lowest price of all wins. They never combine.
- A discount marked stackable is the one explicit exception: after the winner is chosen,
  stackable discounts are applied on top of it one after another, in ascending discount id.
- A discount that does not lower the price is not applied and is not recorded, so a limited-use
  promotion is never spent for nothing. A tie goes to the tier, then to the lowest discount id.
- Not built yet: the reseller price (Phase 4).
"""

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from .discounts import AppliedDiscount, Discount, apply_discount, is_eligible
from .errors import PricingError
from .money import Money

# (tier name, minimum product quantity), lowest threshold first.
TIER_THRESHOLDS: tuple[tuple[str, int], ...] = (
    ("retail", 1),
    ("wholesale", 10),
    ("dealer", 50),
    ("bulk", 200),
)
TIER_NAMES = frozenset(name for name, _ in TIER_THRESHOLDS)


@dataclass(frozen=True)
class PriceLineInput:
    product_id: int
    variant_id: int
    quantity: int
    tiers: Mapping[str, Money]  # only the tiers that are filled in; "retail" is required


@dataclass(frozen=True)
class PricedLine:
    """Everything here is frozen onto the order line, so later changes never rewrite history."""

    variant_id: int
    quantity: int
    tier: str  # the tier whose price applied before any discount
    unit_price: Money  # what the customer pays per item
    line_total: Money
    list_price: Money  # the variant's retail price
    tier_price: Money  # the best tier price, before any discount
    source: str  # "tier" or "discount": where the winning price came from
    discounts: tuple[AppliedDiscount, ...] = ()


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


def _best_tier(line: PriceLineInput, product_quantity: int) -> tuple[str, Money]:
    best_name = "retail"
    best_price = line.tiers["retail"]
    for name, threshold in TIER_THRESHOLDS[1:]:
        price = line.tiers.get(name)
        # "<=": on a tie the higher tier is the one reported.
        if price is not None and product_quantity >= threshold and price <= best_price:
            best_name, best_price = name, price
    return best_name, best_price


def _price_line(
    line: PriceLineInput,
    product_quantity: int,
    discounts: Sequence[Discount],
    now: datetime | None,
) -> PricedLine:
    tier_name, tier_price = _best_tier(line, product_quantity)
    retail = line.tiers["retail"]
    price, source = tier_price, "tier"
    applied: list[AppliedDiscount] = []

    eligible = [
        d
        for d in sorted(discounts, key=lambda d: d.id)
        if now is not None and is_eligible(d, line.product_id, product_quantity, now)
    ]

    # Competition: non-stackable discounts are worked out from retail and the lowest wins.
    winner: Discount | None = None
    for discount in (d for d in eligible if not d.stackable):
        candidate = apply_discount(discount, retail)
        if candidate < price:  # strictly lower, so a tie keeps the tier and the lowest id
            price, winner, source = candidate, discount, "discount"
    if winner is not None:
        applied.append(AppliedDiscount(winner.id, winner.kind, winner.value, price))

    # Explicit stacking: stackable discounts go on top of the winner, in ascending id.
    for discount in (d for d in eligible if d.stackable):
        candidate = apply_discount(discount, price)
        if candidate < price:
            price = candidate
            applied.append(AppliedDiscount(discount.id, discount.kind, discount.value, price))

    return PricedLine(
        variant_id=line.variant_id,
        quantity=line.quantity,
        tier=tier_name,
        unit_price=price,
        line_total=price.times(line.quantity),
        list_price=retail,
        tier_price=tier_price,
        source=source,
        discounts=tuple(applied),
    )


def resolve_price(
    lines: Sequence[PriceLineInput],
    *,
    discounts: Sequence[Discount] = (),
    now: datetime | None = None,
) -> list[PricedLine]:
    """Price every line. Output order matches input order.

    `now` (timezone-aware) is required whenever discounts are supplied. The caller passes the
    time, so this function never reads a clock and the same inputs always give the same prices.
    """
    for line in lines:
        _validate(line)
    if discounts:
        if now is None or now.tzinfo is None:
            raise PricingError("now, with a time zone, is required when discounts are supplied")
        if len({d.id for d in discounts}) != len(discounts):
            raise PricingError("discount ids must be unique")
    product_quantity: dict[int, int] = defaultdict(int)
    for line in lines:
        product_quantity[line.product_id] += line.quantity
    return [_price_line(line, product_quantity[line.product_id], discounts, now) for line in lines]
