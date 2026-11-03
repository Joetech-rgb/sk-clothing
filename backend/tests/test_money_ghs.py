from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from apps.pricing.money import Money


def test_from_ghs_converts_cedis_to_pesewas():
    assert Money.from_ghs(Decimal("12.50")) == Money(1250)
    assert Money.from_ghs(Decimal("0")) == Money(0)
    assert Money.from_ghs(Decimal("1234.56")) == Money(123456)
    assert Money.from_ghs(Decimal("0.05")) == Money(5)


def test_from_ghs_rejects_more_than_two_decimal_places():
    with pytest.raises(ValueError):
        Money.from_ghs(Decimal("12.505"))


def test_from_ghs_rejects_floats_and_non_finite():
    with pytest.raises(TypeError):
        Money.from_ghs(12.5)
    for bad in ("NaN", "Infinity", "-Infinity"):
        with pytest.raises(ValueError):
            Money.from_ghs(Decimal(bad))


def test_to_ghs_always_has_two_decimals():
    assert str(Money(1250).to_ghs()) == "12.50"
    assert str(Money(5).to_ghs()) == "0.05"
    assert str(Money(100).to_ghs()) == "1.00"


@given(pesewas=st.integers(min_value=0, max_value=10**12))
def test_ghs_roundtrip_is_exact(pesewas):
    assert Money.from_ghs(Money(pesewas).to_ghs()) == Money(pesewas)
