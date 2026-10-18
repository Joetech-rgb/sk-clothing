"""Discount rules. Pure Python: no database, no clock, no side effects.

A Discount is plain data that the caller loads from the database and passes to resolve_price()
together with the current time. Nothing here reads a price or a time from a client.

Kinds
- percent: `value` is basis points (1500 = 15%). New price = price x (10000 - value) / 10000,
  rounded half up to a whole pesewa, per unit, before multiplying by the quantity.
- amount: `value` is pesewas taken off each unit. The price never goes below zero.
- price: `value` is a fixed promotional unit price in pesewas.

Eligibility (all must hold): inside the dates, enough of the product in the cart (summed across
variants, like tiers), the product is covered, and uses remain. The date window is half open:
a discount is live at `starts_at` and no longer live at `ends_at`.

Usage limits: this module only reads `uses_remaining`. Counting a use and refusing the last one
atomically happens when the order is created, in the database, not here.
"""

from dataclasses import dataclass
from datetime import datetime

from .errors import PricingError
from .money import Money

PERCENT = "percent"
AMOUNT = "amount"
PRICE = "price"
KINDS = frozenset({PERCENT, AMOUNT, PRICE})
BASIS_POINTS = 10_000


@dataclass(frozen=True)
class Discount:
    id: int
    kind: str
    value: int
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    min_quantity: int = 1
    product_ids: frozenset[int] | None = None  # None means every product
    uses_remaining: int | None = None  # None means unlimited
    stackable: bool = False  # off unless someone turns it on for this discount

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise PricingError(f"discount {self.id}: unknown kind {self.kind!r}")
        if isinstance(self.value, bool) or not isinstance(self.value, int):
            raise PricingError(f"discount {self.id}: value must be a whole number")
        if self.kind == PERCENT and not 1 <= self.value <= BASIS_POINTS:
            raise PricingError(f"discount {self.id}: percent must be 0.01% to 100%")
        if self.kind == AMOUNT and self.value < 1:
            raise PricingError(f"discount {self.id}: amount off must be at least 1 pesewa")
        if self.kind == PRICE and self.value < 0:
            raise PricingError(f"discount {self.id}: promotional price cannot be negative")
        if self.stackable and self.kind == PRICE:
            raise PricingError(f"discount {self.id}: a fixed price cannot be stacked")
        if self.min_quantity < 1:
            raise PricingError(f"discount {self.id}: min_quantity must be at least 1")
        for moment in (self.starts_at, self.ends_at):
            if moment is not None and moment.tzinfo is None:
                raise PricingError(f"discount {self.id}: dates must include a time zone")
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            raise PricingError(f"discount {self.id}: ends_at must be after starts_at")
        if self.product_ids is not None and not self.product_ids:
            raise PricingError(f"discount {self.id}: product list is empty")
        if self.uses_remaining is not None and self.uses_remaining < 0:
            raise PricingError(f"discount {self.id}: uses_remaining cannot be negative")


@dataclass(frozen=True)
class AppliedDiscount:
    """What was applied to a line, in the form frozen onto the order."""

    discount_id: int
    kind: str
    value: int
    unit_price_after: Money


def is_eligible(discount: Discount, product_id: int, product_quantity: int, now: datetime) -> bool:
    if discount.starts_at is not None and now < discount.starts_at:
        return False
    if discount.ends_at is not None and now >= discount.ends_at:
        return False
    if product_quantity < discount.min_quantity:
        return False
    if discount.product_ids is not None and product_id not in discount.product_ids:
        return False
    return discount.uses_remaining is None or discount.uses_remaining > 0


def apply_discount(discount: Discount, base: Money) -> Money:
    """The unit price this discount would give, starting from `base`. Never below zero."""
    if discount.kind == PERCENT:
        pesewas = base.pesewas * (BASIS_POINTS - discount.value) + BASIS_POINTS // 2
        return Money(pesewas // BASIS_POINTS)
    if discount.kind == AMOUNT:
        return Money(max(0, base.pesewas - discount.value))
    return Money(discount.value)
