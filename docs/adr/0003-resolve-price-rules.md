# ADR 0003: resolve_price rules and what is deliberately left out

Status: proposed

## Decision
`apps/pricing/services.resolve_price()` is a pure function. Callers build `PriceLineInput` rows from the catalog; it returns `PricedLine` rows. It never reads a price from a client.

- Tier thresholds are on the quantity of the same product summed across variants: retail 1, wholesale 10, dealer 50, bulk 200.
- Each variant is charged its own tier price.
- Among tiers whose threshold is met and which are filled in, the **lowest price wins** (so a mistyped, dearer higher tier can never raise a price, and price never rises with quantity). On a tie the higher tier is reported.
- Retail is required. A price of 0 is allowed; a negative price is an error.
- Money is `Money(pesewas: int)`. Floats and bools are rejected.

## Left out on purpose
- **Discounts.** CLAUDE.md says "lowest valid price wins" but does not say whether a discount is a percentage, an amount off, or a fixed price. Not guessed. Open question in PROGRESS.md.
- **Reseller price.** Phase 4, visible only in the reseller dashboard.

## Provisional
- `Money` lives in `apps/pricing/money.py` because a shared app would be a new Django app. Move it when a shared home is agreed.
