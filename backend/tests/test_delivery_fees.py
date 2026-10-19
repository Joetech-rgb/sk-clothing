from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from apps.delivery.fees import (
    AWAITING_QUOTE,
    DOORSTEP,
    PICKUP,
    PRICED,
    STATION,
    DoorstepSettings,
    GeoPoint,
    doorstep_quote_for_distance,
    quote_delivery,
    station_fee,
    straight_line_km,
)
from apps.pricing.money import Money

ACCRA = GeoPoint(5.6037, -0.1870)
KUMASI = GeoPoint(6.6885, -1.6244)

SETTINGS = DoorstepSettings(
    shop=ACCRA,
    minimum_fee=Money(1500),
    base_fee=Money(1000),
    rate_per_km=Money(200),
    max_distance_km=Decimal("25"),
)
STATIONS = {"Kaneshie Station": Money(2000), "Circle": Money(1800)}


def doorstep(straight_km):
    return doorstep_quote_for_distance(Decimal(str(straight_km)), SETTINGS)


# --- distance --------------------------------------------------------------------


def test_haversine_matches_known_distances():
    assert 195 < straight_line_km(ACCRA, KUMASI) < 205  # about 200 km as the crow flies
    assert straight_line_km(ACCRA, ACCRA) == 0
    one_degree = straight_line_km(GeoPoint(0, 0), GeoPoint(1, 0))
    assert 111.0 < one_degree < 111.4


def test_distance_is_symmetric():
    assert straight_line_km(ACCRA, KUMASI) == pytest.approx(straight_line_km(KUMASI, ACCRA))


def test_bad_coordinates_are_refused():
    for lat, lng in ((91, 0), (-91, 0), (0, 181), (0, -181), (float("nan"), 0), (0, float("inf"))):
        with pytest.raises(ValueError):
            GeoPoint(lat, lng)
    with pytest.raises(ValueError):
        GeoPoint(True, 0)


# --- doorstep fee --------------------------------------------------------------------


def test_fee_is_base_plus_rate_times_road_km():
    q = doorstep(5)  # road km = 5 x 1.3 = 6.5; fee = 1000 + 200 x 6.5 = 2300
    assert (q.status, q.fee, q.cod_allowed) == (PRICED, Money(2300), True)
    assert q.road_km == Decimal("6.500")


def test_the_minimum_fee_applies_to_short_trips():
    q = doorstep(0.5)  # road 0.65 km; 1000 + 130 = 1130, below the minimum of 1500
    assert q.fee == Money(1500)
    assert doorstep(0).fee == Money(1500)


def test_fee_rounds_half_up_to_a_whole_pesewa():
    settings_ = DoorstepSettings(ACCRA, Money(0), Money(0), Money(333), Decimal("25"))
    assert doorstep_quote_for_distance(Decimal("1"), settings_).fee == Money(433)  # 432.9
    half = DoorstepSettings(ACCRA, Money(0), Money(0), Money(5), Decimal("25"))
    assert doorstep_quote_for_distance(Decimal("0.0769230769"), half).fee == Money(1)  # 0.5 up


def test_the_road_factor_is_a_setting_not_a_constant():
    flat = DoorstepSettings(ACCRA, Money(0), Money(0), Money(100), Decimal("25"), Decimal("1"))
    assert doorstep_quote_for_distance(Decimal("10"), flat).fee == Money(1000)
    assert doorstep_quote_for_distance(Decimal("10"), SETTINGS).road_km == Decimal("13.000")


def test_beyond_the_maximum_distance_awaits_a_quote_and_never_allows_cod():
    q = doorstep(20)  # road 26 km, over the 25 km limit
    assert (q.status, q.fee, q.cod_allowed, q.reason) == (
        AWAITING_QUOTE,
        None,
        False,
        "beyond_max_distance",
    )


def test_exactly_the_maximum_distance_is_still_priced():
    exactly = doorstep_quote_for_distance(Decimal("25") / Decimal("1.3"), SETTINGS)
    assert exactly.status == PRICED  # road km rounds to 25.000, which is not beyond 25
    just_over = doorstep_quote_for_distance(Decimal("19.24"), SETTINGS)  # road 25.012
    assert just_over.status == AWAITING_QUOTE


def test_settings_are_validated():
    bad = [
        lambda: DoorstepSettings(ACCRA, Money(-1), Money(0), Money(0), Decimal("1")),
        lambda: DoorstepSettings(ACCRA, Money(0), Money(0), Money(0), Decimal("0")),
        lambda: DoorstepSettings(ACCRA, Money(0), Money(0), Money(0), Decimal("1"), Decimal("0")),
    ]
    for build in bad:
        with pytest.raises(ValueError):
            build()
    with pytest.raises(ValueError):
        doorstep_quote_for_distance(Decimal("-1"), SETTINGS)


# --- stations and methods --------------------------------------------------------------


def test_station_names_match_ignoring_case_and_spacing():
    assert station_fee("  kaneshie   STATION ", STATIONS) == Money(2000)
    assert station_fee("Madina", STATIONS) is None


def test_pickup_is_free_and_never_pay_on_delivery():
    q = quote_delivery(PICKUP)
    assert (q.status, q.fee, q.cod_allowed) == (PRICED, Money(0), False)


def test_a_listed_station_is_priced_and_an_unlisted_one_awaits_a_quote():
    listed = quote_delivery(STATION, station_name="circle", stations=STATIONS)
    assert (listed.status, listed.fee, listed.cod_allowed) == (PRICED, Money(1800), False)
    unlisted = quote_delivery(STATION, station_name="Tema Station 9", stations=STATIONS)
    assert (unlisted.status, unlisted.fee, unlisted.reason) == (
        AWAITING_QUOTE,
        None,
        "unlisted_station",
    )


def test_a_station_order_needs_a_station_name():
    for blank in (None, "", "   "):
        with pytest.raises(ValueError):
            quote_delivery(STATION, station_name=blank, stations=STATIONS)


def test_doorstep_through_the_main_entry_point():
    near = GeoPoint(5.6100, -0.1900)  # about 0.8 km from the shop
    q = quote_delivery(DOORSTEP, destination=near, doorstep=SETTINGS)
    assert q.method == DOORSTEP and q.status == PRICED and q.cod_allowed
    far = quote_delivery(DOORSTEP, destination=KUMASI, doorstep=SETTINGS)
    assert far.status == AWAITING_QUOTE and not far.cod_allowed


def test_missing_inputs_and_unknown_methods_are_refused():
    with pytest.raises(ValueError):
        quote_delivery(DOORSTEP, doorstep=SETTINGS)
    with pytest.raises(ValueError):
        quote_delivery(DOORSTEP, destination=ACCRA)
    with pytest.raises(ValueError):
        quote_delivery("drone")


# --- properties --------------------------------------------------------------------------

metres = st.integers(min_value=0, max_value=40_000)


@settings(max_examples=2000, deadline=None)
@given(a=metres, b=metres)
def test_the_fee_never_falls_as_the_distance_grows_and_never_beats_the_minimum(a, b):
    near, far = sorted((a, b))
    q_near = doorstep_quote_for_distance(Decimal(near) / 1000, SETTINGS)
    q_far = doorstep_quote_for_distance(Decimal(far) / 1000, SETTINGS)
    for q in (q_near, q_far):
        if q.status == PRICED:
            assert q.fee >= SETTINGS.minimum_fee
    if q_near.status == AWAITING_QUOTE:
        assert q_far.status == AWAITING_QUOTE  # beyond the limit stays beyond it
    elif q_far.status == PRICED:
        assert q_far.fee >= q_near.fee
