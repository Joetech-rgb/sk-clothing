from datetime import datetime, timedelta, timezone

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from apps.pricing.discounts import AMOUNT, PERCENT, PRICE, Discount, apply_discount, is_eligible
from apps.pricing.money import Money
from apps.pricing.services import PriceLineInput, PricingError, resolve_price

NOW = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)
RETAIL_ONLY = {"retail": Money(1000)}
WITH_WHOLESALE = {"retail": Money(1000), "wholesale": Money(900)}


def line(quantity, tiers=None, product_id=1, variant_id=1):
    return PriceLineInput(
        product_id=product_id,
        variant_id=variant_id,
        quantity=quantity,
        tiers=tiers or RETAIL_ONLY,
    )


def price_one(quantity, discounts, tiers=None, now=NOW):
    (priced,) = resolve_price([line(quantity, tiers)], discounts=discounts, now=now)
    return priced


def pct(id, percent, **kwargs):
    return Discount(id=id, kind=PERCENT, value=int(percent * 100), **kwargs)


def off(id, pesewas, **kwargs):
    return Discount(id=id, kind=AMOUNT, value=pesewas, **kwargs)


def promo(id, pesewas, **kwargs):
    return Discount(id=id, kind=PRICE, value=pesewas, **kwargs)


# --- the three kinds -------------------------------------------------------------


def test_percent_amount_and_fixed_price_each_work():
    assert price_one(1, [pct(1, 20)]).unit_price == Money(800)
    assert price_one(1, [off(1, 150)]).unit_price == Money(850)
    assert price_one(1, [promo(1, 700)]).unit_price == Money(700)


def test_percent_rounds_half_up_to_a_whole_pesewa():
    assert apply_discount(pct(1, 10), Money(1005)) == Money(905)  # 904.5 rounds up
    assert apply_discount(pct(1, 15), Money(999)) == Money(849)  # 849.15 rounds down
    assert apply_discount(pct(1, 100), Money(999)) == Money(0)


def test_an_amount_off_never_takes_the_price_below_zero():
    assert price_one(1, [off(1, 5000)]).unit_price == Money(0)


def test_a_dearer_promotional_price_loses():
    priced = price_one(1, [promo(1, 1200)])
    assert priced.unit_price == Money(1000)
    assert priced.discounts == () and priced.source == "tier"


def test_line_total_uses_the_discounted_unit_price():
    assert price_one(3, [pct(1, 10)]).line_total == Money(2700)


# --- lowest valid price wins, no stacking by default -------------------------------


def test_discount_beats_wholesale_when_it_is_cheaper():
    priced = price_one(10, [pct(1, 20)], WITH_WHOLESALE)  # 800 from retail vs 900 wholesale
    assert (priced.unit_price, priced.source, priced.tier) == (Money(800), "discount", "wholesale")
    assert priced.tier_price == Money(900) and priced.list_price == Money(1000)


def test_wholesale_beats_a_weaker_discount_and_the_discount_is_not_spent():
    priced = price_one(10, [pct(1, 5)], WITH_WHOLESALE)  # 950 from retail vs 900 wholesale
    assert (priced.unit_price, priced.source) == (Money(900), "tier")
    assert priced.discounts == ()


def test_a_tie_goes_to_the_tier_so_a_limited_promotion_is_not_used_up():
    priced = price_one(10, [pct(1, 10)], WITH_WHOLESALE)  # 900 from retail ties wholesale 900
    assert priced.source == "tier" and priced.discounts == ()


def test_two_discounts_do_not_combine_the_lowest_one_wins():
    priced = price_one(1, [pct(1, 10), off(2, 300), promo(3, 750)])
    assert priced.unit_price == Money(700)  # 900, 700 and 750 compete; 700 (amount) is lowest
    assert [d.discount_id for d in priced.discounts] == [2]


def test_equal_discounts_resolve_to_the_lowest_id():
    priced = price_one(1, [off(7, 200), off(3, 200)])
    assert [d.discount_id for d in priced.discounts] == [3]


def test_the_winning_discount_is_recorded_in_full_for_the_order():
    (applied,) = price_one(1, [pct(4, 20)]).discounts
    assert (applied.discount_id, applied.kind, applied.value) == (4, PERCENT, 2000)
    assert applied.unit_price_after == Money(800)


# --- explicit stacking ---------------------------------------------------------------


def test_stackable_discounts_apply_on_top_of_the_winner_in_id_order():
    winner = pct(1, 20)  # 1000 -> 800
    extra = off(2, 100, stackable=True)  # 800 -> 700
    priced = price_one(1, [extra, winner])
    assert priced.unit_price == Money(700)
    assert [d.discount_id for d in priced.discounts] == [1, 2]


def test_a_stackable_discount_alone_applies_to_the_tier_price():
    priced = price_one(10, [off(1, 100, stackable=True)], WITH_WHOLESALE)
    assert priced.unit_price == Money(800)  # wholesale 900 minus 100
    assert priced.source == "tier"
    assert [d.discount_id for d in priced.discounts] == [1]


def test_stacking_order_is_by_id_not_by_the_order_given():
    a = pct(1, 10, stackable=True)  # 1000 -> 900
    b = off(2, 150, stackable=True)  # 900 -> 750
    assert price_one(1, [a, b]).unit_price == Money(750)
    assert price_one(1, [b, a]).unit_price == Money(750)  # same answer whatever the input order
    reversed_ids = price_one(1, [pct(2, 10, stackable=True), off(1, 150, stackable=True)])
    assert reversed_ids.unit_price == Money(765)  # 1000 -> 850 -> 765: order really matters


def test_a_fixed_price_cannot_be_marked_stackable():
    with pytest.raises(PricingError):
        promo(1, 500, stackable=True)


def test_a_stackable_discount_that_changes_nothing_is_not_recorded():
    free = price_one(1, [off(1, 100, stackable=True)], {"retail": Money(0)})
    assert free.unit_price == Money(0) and free.discounts == ()
    tiny = price_one(1, [pct(1, 1, stackable=True)], {"retail": Money(1)})  # 1% of 1 pesewa
    assert tiny.unit_price == Money(1) and tiny.discounts == ()


# --- eligibility -------------------------------------------------------------------


def test_dates_are_half_open_live_at_start_and_not_live_at_end():
    d = pct(1, 20, starts_at=NOW, ends_at=NOW + timedelta(days=1))
    assert price_one(1, [d], now=NOW - timedelta(seconds=1)).discounts == ()
    assert price_one(1, [d], now=NOW).unit_price == Money(800)
    assert price_one(1, [d], now=NOW + timedelta(days=1)).discounts == ()


def test_minimum_quantity_is_counted_across_variants_of_the_product():
    d = pct(1, 20, min_quantity=10)
    lines = [line(5, variant_id=1), line(5, variant_id=2)]
    priced = resolve_price(lines, discounts=[d], now=NOW)
    assert [p.unit_price for p in priced] == [Money(800), Money(800)]
    assert price_one(9, [d]).discounts == ()


def test_product_eligibility():
    d = pct(1, 20, product_ids=frozenset({1}))
    inside, outside = resolve_price(
        [line(1, product_id=1), line(1, product_id=2, variant_id=2)], discounts=[d], now=NOW
    )
    assert inside.unit_price == Money(800) and outside.unit_price == Money(1000)


def test_usage_limits():
    assert price_one(1, [pct(1, 20, uses_remaining=0)]).discounts == ()
    assert price_one(1, [pct(1, 20, uses_remaining=1)]).unit_price == Money(800)
    assert price_one(1, [pct(1, 20, uses_remaining=None)]).unit_price == Money(800)


def test_an_exhausted_discount_does_not_block_the_next_best_one():
    priced = price_one(1, [pct(1, 50, uses_remaining=0), pct(2, 10)])
    assert [d.discount_id for d in priced.discounts] == [2]


# --- the clock and bad configuration -------------------------------------------------


def test_discounts_need_a_timezone_aware_now():
    with pytest.raises(PricingError):
        resolve_price([line(1)], discounts=[pct(1, 10)])
    with pytest.raises(PricingError):
        resolve_price([line(1)], discounts=[pct(1, 10)], now=datetime(2026, 11, 20, 12, 0))


def test_no_discounts_needs_no_clock():
    assert resolve_price([line(1)])[0].unit_price == Money(1000)


def test_bad_discount_configuration_is_refused_when_it_is_built():
    bad = [
        lambda: Discount(id=1, kind="bogus", value=1),
        lambda: pct(1, 0),
        lambda: Discount(id=1, kind=PERCENT, value=10001),
        lambda: off(1, 0),
        lambda: promo(1, -1),
        lambda: pct(1, 10, min_quantity=0),
        lambda: pct(1, 10, product_ids=frozenset()),
        lambda: pct(1, 10, uses_remaining=-1),
        lambda: pct(1, 10, starts_at=datetime(2026, 1, 1)),
        lambda: pct(1, 10, starts_at=NOW, ends_at=NOW),
        lambda: Discount(id=1, kind=AMOUNT, value=1.5),
    ]
    for build in bad:
        with pytest.raises(PricingError):
            build()


def test_duplicate_discount_ids_are_refused():
    with pytest.raises(PricingError):
        resolve_price([line(1)], discounts=[pct(1, 10), off(1, 5)], now=NOW)


def test_is_eligible_is_a_plain_yes_or_no():
    d = pct(1, 10, min_quantity=2, product_ids=frozenset({1}), uses_remaining=1)
    assert is_eligible(d, 1, 2, NOW) is True
    assert is_eligible(d, 1, 1, NOW) is False
    assert is_eligible(d, 2, 2, NOW) is False


# --- properties and a second, independent implementation ------------------------------

price = st.integers(min_value=0, max_value=100_000)
optional_price = st.one_of(st.none(), price)
kind = st.sampled_from([PERCENT, AMOUNT, PRICE])
discount_spec = st.tuples(
    kind,
    st.integers(min_value=1, max_value=10_000),  # value, bounded per kind below
    st.integers(min_value=1, max_value=60),  # min quantity
    st.booleans(),  # stackable
    st.integers(min_value=0, max_value=3),  # uses: 0 means exhausted, 3 means unlimited
    st.integers(min_value=-1, max_value=1),  # date window: -1 not started, 0 live, 1 ended
)
quantity = st.integers(min_value=1, max_value=300)


def build_discounts(specs):
    built = []
    for index, (kind_, raw, min_q, stackable, uses, window) in enumerate(specs, start=1):
        if kind_ == PERCENT:
            value = min(raw, 10_000)
        elif kind_ == AMOUNT:
            value = raw
        else:
            value = raw % 2000
            stackable = False
        starts = NOW + timedelta(days=1) if window == -1 else NOW - timedelta(days=1)
        ends = NOW - timedelta(hours=1) if window == 1 else NOW + timedelta(days=3)
        if window == 1:
            starts = NOW - timedelta(days=2)
        built.append(
            Discount(
                id=index,
                kind=kind_,
                value=value,
                starts_at=starts,
                ends_at=ends,
                min_quantity=min_q,
                stackable=stackable,
                uses_remaining=None if uses == 3 else uses,
            )
        )
    return built


def tiers_from(retail, wholesale, dealer, bulk):
    tiers = {"retail": Money(retail)}
    for name, value in (("wholesale", wholesale), ("dealer", dealer), ("bulk", bulk)):
        if value is not None:
            tiers[name] = Money(value)
    return tiers


def reference_price(tiers, quantity, discounts, now):
    """A deliberately plain second implementation of the written rules, for comparison."""
    thresholds = {"retail": 1, "wholesale": 10, "dealer": 50, "bulk": 200}
    tier_price = min(p.pesewas for n, p in tiers.items() if quantity >= thresholds[n])
    retail = tiers["retail"].pesewas

    def live(d):
        return (
            (d.starts_at is None or d.starts_at <= now)
            and (d.ends_at is None or now < d.ends_at)
            and quantity >= d.min_quantity
            and (d.uses_remaining is None or d.uses_remaining > 0)
        )

    def after(d, base):
        if d.kind == PERCENT:
            return (base * (10_000 - d.value) + 5_000) // 10_000
        if d.kind == AMOUNT:
            return max(0, base - d.value)
        return d.value

    best = tier_price
    for d in discounts:
        if live(d) and not d.stackable:
            best = min(best, after(d, retail))
    for d in sorted(discounts, key=lambda d: d.id):
        if live(d) and d.stackable:
            best = min(best, after(d, best))
    return best


@settings(max_examples=2000, deadline=None)
@given(
    retail=price,
    wholesale=optional_price,
    dealer=optional_price,
    bulk=optional_price,
    q=quantity,
    specs=st.lists(discount_spec, min_size=0, max_size=4),
)
def test_matches_an_independent_implementation_and_never_misbehaves(
    retail, wholesale, dealer, bulk, q, specs
):
    tiers = tiers_from(retail, wholesale, dealer, bulk)
    discounts = build_discounts(specs)
    priced = price_one(q, discounts, tiers)
    assert priced.unit_price.pesewas == reference_price(tiers, q, discounts, NOW)
    assert priced.unit_price.pesewas >= 0
    assert priced.unit_price <= priced.tier_price <= priced.list_price  # discounts never raise it
    assert priced.line_total == Money(priced.unit_price.pesewas * q)
    # every recorded discount really lowered the price when it was applied
    steps = [priced.tier_price, *[d.unit_price_after for d in priced.discounts]]
    ids = [d.discount_id for d in priced.discounts]
    assert len(set(ids)) == len(ids)
    assert all(before > after for before, after in zip(steps, steps[1:], strict=False))
    assert steps[-1] == priced.unit_price  # the last step is the final price


@settings(max_examples=1500, deadline=None)
@given(
    retail=price,
    wholesale=optional_price,
    dealer=optional_price,
    bulk=optional_price,
    q1=quantity,
    q2=quantity,
    specs=st.lists(discount_spec, min_size=0, max_size=4),
)
def test_buying_more_never_costs_more_per_item_even_with_discounts(
    retail, wholesale, dealer, bulk, q1, q2, specs
):
    tiers = tiers_from(retail, wholesale, dealer, bulk)
    discounts = build_discounts(specs)
    low, high = sorted((q1, q2))
    cheaper = price_one(high, discounts, tiers).unit_price
    assert cheaper <= price_one(low, discounts, tiers).unit_price
