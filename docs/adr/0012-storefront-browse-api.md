# ADR 0012: Storefront browse API

Status: proposed.

## What is built
Public, read-only endpoints under `/api/v1/catalog/`, plus one pricing endpoint:

| Endpoint | Purpose |
|---|---|
| `GET categories/` | Active categories, ordered by position then name |
| `GET products/` | A page of products: filter by category (includes sub-categories), search text, sort (relevance, newest, price low, price high), `limit` up to 50, an opaque `cursor` |
| `GET products/<slug>/` | One product: images, variants with only their filled price tiers, stock left, and the quantity thresholds ("10 or more of any size or colour") |
| `POST price/` | Prices a basket from variant ids and quantities through `resolve_price()` |

## Decisions
1. **Only things that can be bought are shown.** Active product, active category, and at least one
   active variant with a retail price. A variant with no retail price is hidden, never shown at a
   wrong price.
2. **The browser never names a price.** `price/` accepts variant ids and quantities only. Any other
   field (a price, a tier, a discount) is a 400, not silently ignored, so a tampering attempt is
   visible. Prices go out as whole pesewas plus a display string; the browser only displays them.
3. **Search sits behind `SearchService`.** The Postgres version combines full-text matching on name
   (weighted higher) and description with trigram word similarity, so "kenta" finds "Kente". The
   input is normalised and uses Postgres web-search syntax, so quotes, operators and control
   characters cannot break the query. `SEARCH_BACKEND` is a setting; Phase 1B points it at
   Meilisearch and no caller changes.
4. **Cursor paging.** The cursor is opaque, carries an offset, and a made-up or tampered cursor is a
   400. Offsets are capped at 10,000, so nobody can request an arbitrarily expensive page.
5. **A fixed number of queries per page** (about six) however many products it holds, with a test
   that fails if it grows.
6. **Cloudflare caching.** Successful reads carry `Cache-Control: public` with short lifetimes
   (categories 5 minutes, product lists 1 minute, product pages 30 seconds, each with
   stale-while-revalidate). Errors and the pricing endpoint are not cached. Public views carry no
   session, so they set no cookie and need no CSRF check. **Stock left can be up to 30 seconds old
   on a page; the reservation at checkout is the authority, so this can never cause overselling.**
7. **Unavailable items.** Pricing a variant that is withdrawn or has no retail price is a 422 with
   the stable code `variant_unavailable` and the variant id, so the cart can remove that line.
8. **Trigram extension.** Migration `0002` enables `pg_trgm`. The database user must be allowed to
   create extensions (true for the Docker Postgres used in CI and on the VPS).

## Not built yet
- Filters by size, colour and price range (the brief lists "categories and filters"; I need to know
  which filters the shop wants before building them).
- Responsive image sets (`srcset`). Images are a single URL until the photo pipeline stores the
  resized files; `MEDIA_BASE_URL` points at the R2 public domain.
- A trigram index on product names. Unneeded at a few thousand products; add it when the load test
  shows search is slow.
- Discounts in the basket price (the Discount table is not built; the response already carries the
  `discounts` list for it).
- Product counts per category and "in stock only" filtering (stock lives in another app, so a join
  is not allowed; it needs a different design if wanted).
