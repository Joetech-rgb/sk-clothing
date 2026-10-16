import pytest
from hypothesis import given
from hypothesis import strategies as st

from apps.pricing.money import Money
from apps.pricing.services import PriceLineInput, PricingError, resolve_price

FULL = {"retail": 1000, "wholesale": 900, "dealer": 800, "bulk": 700}


def _tiers(retail, wholesale=None, dealer=None, bulk=None):
    tiers = {"retail": Money(retail)}
    for name, value in (("wholesale", wholesale), ("dealer", dealer), ("bulk", bulk)):
        if value is not None:
            tiers[name] = Money(value)
    return tiers


def _line(quantity, tiers, product_id=1, variant_id=1):
    return PriceLineInput(
        product_id=product_id, variant_id=variant_id, quantity=quantity, tiers=tiers
    )


def _unit(tiers, quantity):
    (priced,) = resolve_price([_line(quantity, tiers)])
    return priced.unit_price.pesewas


# --- tier boundaries -------------------------------------------------------------


def test_every_tier_boundary():
    tiers = _tiers(**FULL)
    expected = {
        1: 1000, 9: 1000,
        10: 900, 49: 900,
        50: 800, 199: 800,
        200: 700, 500: 700,
    }  # fmt: skip
    for quantity, price in expected.items():
        assert _unit(tiers, quantity) == price, quantity


def test_tier_name_is_reported():
    tiers = _tiers(**FULL)
    names = {q: resolve_price([_line(q, tiers)])[0].tier for q in (9, 10, 50, 200)}
    assert names == {9: "retail", 10: "wholesale", 50: "dealer", 200: "bulk"}


def test_line_total_is_exact_integer_pesewas():
    (priced,) = resolve_price([_line(3, _tiers(1050))])
    assert priced.line_total == Money(3150)


# --- quantity across variants ----------------------------------------------------


def test_quantity_is_summed_across_variants_and_each_uses_its_own_price():
    red = _line(5, _tiers(1000, wholesale=900), variant_id=1)
    blue = _line(5, _tiers(1200, wholesale=1100), variant_id=2)
    red_priced, blue_priced = resolve_price([red, blue])
    assert (red_priced.tier, red_priced.unit_price) == ("wholesale", Money(900))
    assert (blue_priced.tier, blue_priced.unit_price) == ("wholesale", Money(1100))


def test_different_products_are_not_summed():
    a = _line(5, _tiers(1000, wholesale=900), product_id=1, variant_id=1)
    b = _line(5, _tiers(1000, wholesale=900), product_id=2, variant_id=2)
    assert [p.tier for p in resolve_price([a, b])] == ["retail", "retail"]


def test_output_order_matches_input_order():
    lines = [_line(1, _tiers(100 * i), variant_id=i) for i in (3, 1, 2)]
    assert [p.variant_id for p in resolve_price(lines)] == [3, 1, 2]


# --- missing tiers ---------------------------------------------------------------


def test_missing_tiers_are_skipped():
    only_bulk = _tiers(1000, bulk=700)
    assert _unit(only_bulk, 10) == 1000
    assert _unit(only_bulk, 200) == 700
    only_dealer = _tiers(1000, dealer=800)
    assert _unit(only_dealer, 10) == 1000
    assert _unit(only_dealer, 60) == 800


def test_retail_only_variant_is_always_retail():
    assert _unit(_tiers(1000), 500) == 1000


def test_lowest_price_wins_if_a_higher_tier_was_entered_dearer():
    # Data entry mistake: wholesale dearer than retail. The customer never pays more.
    assert _unit(_tiers(1000, wholesale=1100), 10) == 1000


# --- invalid input ---------------------------------------------------------------


def test_missing_retail_price_is_an_error():
    with pytest.raises(PricingError):
        resolve_price([_line(1, {"wholesale": Money(900)})])


def test_bad_quantity_is_an_error():
    for bad in (0, -1, 1.5, True):
        with pytest.raises(PricingError):
            resolve_price([_line(bad, _tiers(1000))])


def test_negative_price_is_an_error():
    with pytest.raises(PricingError):
        resolve_price([_line(1, {"retail": Money(-1)})])


def test_unknown_tier_is_an_error():
    with pytest.raises(PricingError):
        resolve_price([_line(1, {"retail": Money(1000), "reseller": Money(500)})])


# --- Money -----------------------------------------------------------------------


def test_money_rejects_floats_and_bools():
    for bad in (10.5, True, "100", None):
        with pytest.raises(TypeError):
            Money(bad)


def test_money_formatting():
    assert str(Money(1250)) == "GHS 12.50"
    assert str(Money(5)) == "GHS 0.05"
    assert str(Money(123456)) == "GHS 1,234.56"


def test_money_adds_exactly():
    assert Money(10) + Money(5) == Money(15)


# --- properties ------------------------------------------------------------------

price = st.integers(min_value=0, max_value=1_000_000)
optional_price = st.one_of(st.none(), price)
quantity = st.integers(min_value=1, max_value=400)


@given(
    retail=price,
    wholesale=optional_price,
    dealer=optional_price,
    bulk=optional_price,
    q1=quantity,
    q2=quantity,
)
def test_unit_price_never_rises_as_quantity_grows(retail, wholesale, dealer, bulk, q1, q2):
    tiers = _tiers(retail, wholesale, dealer, bulk)
    low, high = sorted((q1, q2))
    assert _unit(tiers, high) <= _unit(tiers, low)


@given(
    retail=price,
    wholesale=optional_price,
    dealer=optional_price,
    bulk=optional_price,
    q=quantity,
)
def test_price_is_never_negative_and_is_always_one_of_the_tier_prices(
    retail, wholesale, dealer, bulk, q
):
    tiers = _tiers(retail, wholesale, dealer, bulk)
    (priced,) = resolve_price([_line(q, tiers)])
    assert priced.unit_price.pesewas >= 0
    assert priced.unit_price in tiers.values()
    assert priced.unit_price <= tiers["retail"]
    assert priced.line_total == Money(priced.unit_price.pesewas * q)
