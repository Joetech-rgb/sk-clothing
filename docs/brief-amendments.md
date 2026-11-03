# Amendments to CLAUDE.md (client answers of 2026-10-18)

Paste into CLAUDE.md. Items marked CONFIRM are my interpretation and await the client.

## Section 5, Pricing and discounts (replace the discount bullet)
- Discount kinds: percentage, fixed amount off, fixed promotional price. Each can have dates,
  a minimum quantity (summed across the product's variants), product eligibility and a usage limit.
- Stacking is off by default and only happens for a discount explicitly marked stackable.
- Lowest valid and eligible price wins. A non-stackable discount is worked from the retail price
  and competes with the best tier price (CONFIRM). See ADR 0007.
- The applied tier, tier price, list price and each discount are frozen on the order line.

## Section 5, Orders and payments (add)
- A payment verified after the 15-minute hold expired: re-reserve the stock in one atomic
  transaction. If available, continue the order. If not, never oversell: refund to the original
  payment method and track it to confirmation. Payment, fulfilment and refund status are separate
  fields. Failed refunds retry, then go to manual resolution. The customer is told the outcome.
  See ADR 0008.

## Section 7 or 12 (add)
- Hosting: Hostinger KVM 2 (2 vCPU, 8 GB RAM, 100 GB NVMe, 8 TB bandwidth) to start.
- Capacity test targets, not guarantees: launch 100 concurrent visitors, 5,000 products, 30 orders
  an hour; stretch 500, 10,000 and 60 (CONFIRM which is the pass mark). Capacity is decided by
  load testing. Before production launch: load tests, monitoring, backups, a tested recovery and a
  documented upgrade path (ADR 0009).
- Architecture: modular monolith now, built so it can move beyond one server later.

## Section 12 (remove the answered items)
Answered: discount definition, late-payment rule, VPS plan size, traffic numbers.
