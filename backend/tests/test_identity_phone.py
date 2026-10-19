import pytest
from hypothesis import given
from hypothesis import strategies as st

from apps.identity.phone import InvalidPhone, mask_phone, normalise_ghana_phone

E164 = "+233241234567"


def test_every_common_spelling_gives_the_same_number():
    spellings = [
        "0241234567",
        "024 123 4567",
        "024-123-4567",
        "(024) 123 4567",
        "241234567",
        "233241234567",
        "+233241234567",
        "+233 24 123 4567",
        "+233-24-123-4567",
        "00233241234567",
        "00233 24 123 4567",
        "  0241234567  ",
        "024.123.4567",
    ]
    for raw in spellings:
        assert normalise_ghana_phone(raw) == E164, raw


def test_numbers_that_are_not_ghana_numbers_are_refused():
    bad = [
        "",
        "   ",
        "024123456",  # too short
        "02412345678",  # too long
        "+2332412345",  # too short
        "+23324123456789",  # too long
        "+14155552671",  # a US number
        "004155552671",
        "0041234567",
        "+233041234567",  # national part may not start with 0
        "abc",
        "024123456a",
        "+233 24 123 45 6x",
        "٠٢٤١٢٣٤٥٦٧",  # Arabic-Indic digits
        "٢٤١٢٣٤٥٦٧",  # nine Arabic-Indic digits: must not pass as a national number
        "２４１２３４５６７",  # nine full-width digits
        "+233２４１２３４５６７",
        "+447911123456",  # a UK number whose last nine digits look like a Ghana number
        "00447911123456",
        "+2332",  # country code only
        "024 123 4567 ext 2",
        "++233241234567",
    ]
    for raw in bad:
        with pytest.raises(InvalidPhone):
            normalise_ghana_phone(raw)


def test_non_text_is_refused():
    for bad in (None, 241234567, 1.5, b"0241234567"):
        with pytest.raises(InvalidPhone):
            normalise_ghana_phone(bad)


def test_normalising_twice_changes_nothing():
    assert normalise_ghana_phone(normalise_ghana_phone("0241234567")) == E164


def test_masking_hides_the_middle_and_keeps_the_length():
    masked = mask_phone(E164)
    assert masked == "+233******567"
    assert len(masked) == len(E164)
    assert "2412345" not in masked
    assert mask_phone("123") == "***"


@given(national=st.integers(min_value=100_000_000, max_value=999_999_999))
def test_any_valid_national_number_normalises_consistently(national):
    expected = f"+233{national}"
    assert normalise_ghana_phone(f"0{national}") == expected
    assert normalise_ghana_phone(f"+233{national}") == expected
    assert normalise_ghana_phone(f"00233{national}") == expected
    assert normalise_ghana_phone(str(national)) == expected
