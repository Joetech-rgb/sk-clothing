# ADR 0004: Catalog model and what is deliberately left out

Status: proposed

## Decision
New `catalog` app: `Category`, `Product`, `Variant`, `PriceTier`, `ProductImage`.

- A variant has one `PriceTier` row per filled tier (retail, wholesale, dealer, bulk). Prices are whole pesewas (`PositiveBigIntegerField`, so the database refuses negatives). One row per variant and tier is a database constraint.
- Staff type cedis in the admin (12.50). `Money.from_ghs` converts with `Decimal`, never floats, and rejects more than two decimal places.
- A variant needs a retail price. The admin refuses to save a variant without one. A variant created from the product page has no prices until its tiers are added, and the variant list shows `MISSING`.
- `price_cart()` is the one catalog service for pricing. It takes variant ids and quantities, never prices, uses two queries however many items, and calls `resolve_price()`.
- The tier names are duplicated between `PriceTier.Tier` and `pricing.services.TIER_NAMES`. A test fails if they drift.

## Left out on purpose
- **Photo upload and WebP resizing.** Needs `boto3` and `Pillow`, which need approval. `ProductImage` stores a storage key only.
- **Price history** (`django-simple-history` on prices). The migration for a history table is easy to get wrong by hand and nothing here can run `makemigrations`. Next pull request.
- **Discounts**, **vendor** on `Product`, **reseller price**, **favourites**, **video**. Later phases or open questions.
- **TOTP two-factor for staff** is required by the brief and is not part of this change.
