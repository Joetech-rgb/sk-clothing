# ADR 0007: Discount rules in resolve_price

Status: proposed. Several points below are my interpretation of the client's answer and need
confirmation (marked CONFIRM).

## Client requirement (2026-10-18)
Percentage, fixed-amount and fixed promotional-price discounts. No stacking unless explicitly
configured. Keep the four tiers and the rule that the lowest valid and eligible price wins.
Promotion dates, minimum quantities, product eligibility and usage limits. All pricing server
side through `resolve_price()`, with the applied pricing details frozen on the order.

## What is built (pure function, no database)
`Discount` is plain data; the caller loads it and passes it with the current time. Same inputs
always give the same prices. With no discounts supplied nothing changes (the 18 existing tests
pass unchanged).

| Kind | `value` | New unit price |
|---|---|---|
| percent | basis points (1500 = 15%) | price x (10000 - value) / 10000, rounded half up to a pesewa, per unit |
| amount | pesewas off each unit | price - value, never below zero |
| price | pesewas | that fixed price |

Eligibility: inside the dates, enough of the product in the cart, product covered, uses remain.

## Interpretations
1. **Discounts compete with tiers; they do not combine with them (CONFIRM).** A non-stackable
   discount is worked out from the variant's retail price. The lowest of {best tier price, each
   eligible discount's price} wins. Example: retail 1000, wholesale 900 at 10 pieces. A 20% discount
   gives 800 and wins; a 5% discount gives 950 and loses. This is how I read "lowest valid price
   wins" together with "no stacking by default". The other reading (discount on top of the tier
   price) is stacking, which you asked to keep off.
2. **Stacking is per discount and explicit (CONFIRM).** A discount with `stackable=True` is applied
   on top of the winner, after it, in ascending discount id. A fixed price cannot be stackable.
   Order matters (10% then 150 off is not 150 off then 10%), so the order is fixed and tested.
3. **A discount that does not lower the price is not applied and not recorded.** A tie goes to the
   tier, then to the lowest discount id. This means a limited-use promotion is never spent for
   nothing.
4. **Minimum quantity is counted across the product's variants**, the same as tiers.
5. **Dates are half open:** live at `starts_at`, not live at `ends_at`. Times must carry a time
   zone. `now` is passed in, never read from a clock inside the function.
6. **Rounding:** half up, per unit, then multiplied by the quantity.
7. **An amount larger than the price gives price 0, not a negative price (CONFIRM).** Recommendation:
   when the admin screen is built, refuse an amount off that is at or above the cheapest price.
8. **Product eligibility is by product only.** Category-level or variant-level eligibility is not
   built (CONFIRM whether wanted).

## Frozen on the order
Each `PricedLine` carries what an order line must store: `unit_price`, `tier`, `tier_price`,
`list_price`, `source` ("tier" or "discount") and `discounts` (id, kind, value and the unit price
after each step). Later price or discount changes never rewrite an order.

## Usage limits (design for the orders phase)
The function only reads `uses_remaining`. Spending a use must be atomic in the database, for
example `UPDATE ... SET uses_remaining = uses_remaining - 1 WHERE id = ? AND uses_remaining > 0`
inside the order transaction. A use should be held with the stock hold (15 minutes) and given back
if the customer does not pay, like stock. CONFIRM: does a "use" mean one order, or one item?
Recommendation: one order. If the last use is taken between cart and checkout, the order is
priced again by the server and the customer sees the new total before paying.

## Not built yet
The Discount table and its admin screen, loading discounts into `catalog.price_cart()`, coupon
codes (not requested), per-customer limits (not requested), scheduled-discount screens (item 5 on
the Stage 1 cut line).
