import pytest
from hypothesis import given
from hypothesis import strategies as st

from apps.catalog.cursor import MAX_OFFSET, decode_cursor, encode_cursor
from apps.catalog.presenters import money_json, price_from, quantity_rules, tier_rows
from apps.catalog.tree import with_descendants
from apps.pricing.money import Money

# --- cursors ---------------------------------------------------------------------


def test_a_cursor_round_trips_and_none_means_the_first_page():
    assert decode_cursor(None) == 0 and decode_cursor("") == 0
    for offset in (0, 1, 24, 48, 9999, MAX_OFFSET):
        assert decode_cursor(encode_cursor(offset)) == offset


@given(offset=st.integers(min_value=0, max_value=MAX_OFFSET))
def test_every_valid_offset_survives_encoding(offset):
    assert decode_cursor(encode_cursor(offset)) == offset


def test_made_up_or_tampered_cursors_are_refused():
    import base64

    def forge(text):
        return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")

    bad = [
        "not-a-cursor",
        "!!!!",
        "%%%",
        forge("o:-1"),
        forge("o:abc"),
        forge("x:5"),
        forge("o:5; DROP TABLE"),
        forge(f"o:{MAX_OFFSET + 1}"),
        forge("o:99999999"),
        forge("o:"),
        "a" * 200,
    ]
    for value in bad:
        with pytest.raises(ValueError):
            decode_cursor(value)


def test_offsets_outside_the_range_cannot_be_issued():
    for offset in (-1, MAX_OFFSET + 1):
        with pytest.raises(ValueError):
            encode_cursor(offset)


# --- category trees ----------------------------------------------------------------


def test_a_category_includes_everything_beneath_it():
    children = {None: [1, 2], 1: [3, 4], 3: [5], 2: [6]}
    assert with_descendants(children, 1) == {1, 3, 4, 5}
    assert with_descendants(children, 2) == {2, 6}
    assert with_descendants(children, 5) == {5}
    assert with_descendants(children, 99) == {99}


def test_a_loop_in_bad_data_does_not_hang():
    assert with_descendants({1: [2], 2: [3], 3: [1]}, 1) == {1, 2, 3}


# --- presenters ----------------------------------------------------------------------


def test_money_goes_out_as_pesewas_and_a_display_string():
    assert money_json(Money(1250)) == {"pesewas": 1250, "display": "GHS 12.50"}


def test_only_filled_tiers_are_shown_cheapest_quantity_first():
    tiers = {"bulk": Money(700), "retail": Money(1000), "wholesale": Money(900)}
    rows = tier_rows(tiers)
    assert [(r["tier"], r["min_quantity"]) for r in rows] == [
        ("retail", 1),
        ("wholesale", 10),
        ("bulk", 200),
    ]
    assert rows[1]["price"] == {"pesewas": 900, "display": "GHS 9.00"}
    assert tier_rows({"retail": Money(1000)}) == [
        {"tier": "retail", "min_quantity": 1, "price": money_json(Money(1000))}
    ]
    assert tier_rows({}) == []


def test_price_from_is_the_cheapest_retail_price():
    variants = [{"retail": Money(1200)}, {"retail": Money(900), "wholesale": Money(800)}]
    assert price_from(variants) == Money(900)
    assert price_from([{"wholesale": Money(500)}]) is None  # nothing sellable
    assert price_from([]) is None


def test_quantity_rules_list_thresholds_that_exist_on_any_variant():
    variants = [{"retail": Money(1000), "wholesale": Money(900)}, {"retail": Money(1100)}]
    assert quantity_rules(variants) == [{"tier": "wholesale", "min_quantity": 10}]
    assert quantity_rules([{"retail": Money(1000)}]) == []
