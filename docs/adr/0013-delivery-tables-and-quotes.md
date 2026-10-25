# ADR 0013: Delivery tables, admin screens and the quote endpoint

Status: proposed.

## What is built
- **Station table** (admin-managed): name, fee in whole pesewas, active flag. Names match ignoring
  case and spacing, and the admin refuses a duplicate in another spelling.
- **Delivery settings** (admin-managed, exactly one record): shop latitude and longitude, minimum
  fee, base fee, rate per km, maximum distance, road factor (default 1.30, from the brief). The
  database refuses a second record, a zero distance and a zero road factor.
- **Staff type cedis, the database stores pesewas.** The admin forms convert with exact decimal
  arithmetic and refuse more than two decimal places.
- **`GET /api/v1/delivery/stations/`** lists active stations and fees for the checkout dropdown
  (cached for a few minutes).
- **`POST /api/v1/delivery/quote/`** takes a method (pickup, station, doorstep) and where to
  (a station name, or the map pin's latitude and longitude) and returns the fee, whether it is
  priced or awaiting a quote, whether pay on delivery is allowed, and why a quote is awaited.
  It accepts nothing else, so a client cannot name its own fee. Never cached.

## Decisions
1. **No numbers are invented.** The shop location and fee values are still open client questions.
   Until staff fill in the delivery settings, every doorstep order is "awaiting quote" with the
   reason `not_configured`, and pay on delivery is not offered. Entering the settings in the admin
   switches distance pricing on with no code change. Stored settings that cannot be used (for
   example a latitude of 95) are treated the same way, with a warning in the log.
2. **Unlisted or switched-off stations are "awaiting quote"**, as the brief requires, until staff
   set a fee.
3. **Pay on delivery** is offered only when a doorstep order could be priced inside the maximum
   distance (ADR 0010 interpretation 1).
4. **Apps stay separate.** Shared response shapes (money formatting, the strict request check,
   the public-view helpers) live in `config`, so delivery imports nothing from the catalog. The
   catalog was moved onto the same helpers.

## Not built yet
- Storing a quote on an order, the delivery code on an order, and the "set the fee, then the
  customer pays" flow for awaiting-quote orders (all part of orders).
- The separate section tracking delivery fees collected and paid to couriers (brief section 5;
  it must never mix with inventory or revenue). Phase 2.
- Rate limits specific to the quote endpoint, which does a little map arithmetic and one or two
  queries. The default per-address limit applies for now.

## What the client still needs to provide
The shop's location, the doorstep fee values and maximum distance, and the station list with fees.
All are entered in the admin, not in code.
