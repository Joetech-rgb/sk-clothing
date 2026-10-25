from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction

from apps.delivery.fees import AWAITING_QUOTE, DOORSTEP, PICKUP, PRICED, STATION
from apps.delivery.models import DeliverySettings, Station
from apps.delivery.services import get_quote, load_doorstep_settings, station_fees
from apps.pricing.money import Money

QUOTE = "/api/v1/delivery/quote/"
STATIONS = "/api/v1/delivery/stations/"

# The shop is in central Accra. These numbers are for tests only; the real ones are set by staff.
SHOP = {"shop_latitude": Decimal("5.603700"), "shop_longitude": Decimal("-0.187000")}


@pytest.fixture
def configured(db):
    return DeliverySettings.objects.create(
        **SHOP,
        minimum_fee_pesewas=1500,
        base_fee_pesewas=1000,
        rate_per_km_pesewas=200,
        max_distance_km=Decimal("25.00"),
    )


@pytest.fixture
def stations(db):
    Station.objects.create(name="Kaneshie Station", fee_pesewas=2000)
    Station.objects.create(name="Circle", fee_pesewas=1800)
    Station.objects.create(name="Closed Down", fee_pesewas=999, is_active=False)


def post(client, **body):
    return client.post(QUOTE, body, content_type="application/json")


# --- models ------------------------------------------------------------------------------


@pytest.mark.django_db
def test_station_names_are_tidied_and_cannot_repeat_in_another_spelling():
    station = Station.objects.create(name="  Kaneshie    Station ", fee_pesewas=2000)
    assert station.name == "Kaneshie Station" and station.name_key == "kaneshie station"
    with pytest.raises(IntegrityError), transaction.atomic():
        Station.objects.create(name="KANESHIE station", fee_pesewas=1)


@pytest.mark.django_db
def test_only_one_settings_row_can_exist(configured):
    assert configured.pk == 1
    duplicate = DeliverySettings(
        id=2, **SHOP, minimum_fee_pesewas=1, base_fee_pesewas=1, rate_per_km_pesewas=1,
        max_distance_km=Decimal("1"),
    )  # fmt: skip
    with pytest.raises(IntegrityError), transaction.atomic():
        DeliverySettings.objects.bulk_create([duplicate])  # skips save(): the database refuses
    configured.base_fee_pesewas = 1200
    configured.save()
    assert DeliverySettings.objects.count() == 1


@pytest.mark.django_db
def test_the_database_refuses_a_zero_distance_or_factor(configured):
    with pytest.raises(IntegrityError), transaction.atomic():
        DeliverySettings.objects.filter(pk=1).update(max_distance_km=Decimal("0"))
    with pytest.raises(IntegrityError), transaction.atomic():
        DeliverySettings.objects.filter(pk=1).update(road_factor=Decimal("0"))


# --- services -------------------------------------------------------------------------------


@pytest.mark.django_db
def test_settings_load_into_the_fee_rules_and_are_none_until_configured():
    assert load_doorstep_settings() is None
    DeliverySettings.objects.create(
        **SHOP, minimum_fee_pesewas=1500, base_fee_pesewas=1000, rate_per_km_pesewas=200,
        max_distance_km=Decimal("25"),
    )  # fmt: skip
    loaded = load_doorstep_settings()
    assert loaded.minimum_fee == Money(1500) and loaded.road_factor == Decimal("1.30")
    assert loaded.shop.lat == pytest.approx(5.6037)


@pytest.mark.django_db
def test_only_active_stations_are_priced(stations):
    assert station_fees() == {"Kaneshie Station": Money(2000), "Circle": Money(1800)}


@pytest.mark.django_db
def test_pickup_is_free_and_stations_use_the_table(stations):
    pickup = get_quote(PICKUP)
    assert (pickup.status, pickup.fee) == (PRICED, Money(0))
    listed = get_quote(STATION, station_name="  circle ")
    assert (listed.status, listed.fee) == (PRICED, Money(1800))
    unlisted = get_quote(STATION, station_name="Madina")
    assert (unlisted.status, unlisted.reason) == (AWAITING_QUOTE, "unlisted_station")
    closed = get_quote(STATION, station_name="Closed Down")
    assert closed.status == AWAITING_QUOTE


@pytest.mark.django_db
def test_doorstep_nearby_is_priced_and_allows_pay_on_delivery(configured):
    quote = get_quote(DOORSTEP, latitude=5.6100, longitude=-0.1900)
    assert quote.status == PRICED and quote.cod_allowed and quote.fee >= Money(1500)


@pytest.mark.django_db
def test_doorstep_far_away_awaits_a_quote_and_never_allows_pay_on_delivery(configured):
    quote = get_quote(DOORSTEP, latitude=6.6885, longitude=-1.6244)  # Kumasi
    assert (quote.status, quote.fee, quote.cod_allowed) == (AWAITING_QUOTE, None, False)
    assert quote.reason == "beyond_max_distance"


@pytest.mark.django_db
def test_without_settings_doorstep_waits_for_a_staff_quote_and_no_number_is_invented():
    quote = get_quote(DOORSTEP, latitude=5.61, longitude=-0.19)
    assert (quote.status, quote.fee, quote.cod_allowed, quote.reason) == (
        AWAITING_QUOTE,
        None,
        False,
        "not_configured",
    )


@pytest.mark.django_db
def test_unusable_stored_settings_fall_back_to_awaiting_a_quote(configured):
    DeliverySettings.objects.filter(pk=1).update(shop_latitude=Decimal("95"))
    assert load_doorstep_settings() is None
    assert get_quote(DOORSTEP, latitude=5.6, longitude=-0.19).reason == "not_configured"


# --- the API -------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_station_list_is_public_cached_and_shows_active_stations_only(client, stations):
    response = client.get(STATIONS)
    assert response.status_code == 200 and not response.cookies
    assert "public" in response["Cache-Control"]
    assert response.json() == [
        {"name": "Circle", "fee": {"pesewas": 1800, "display": "GHS 18.00"}},
        {"name": "Kaneshie Station", "fee": {"pesewas": 2000, "display": "GHS 20.00"}},
    ]


@pytest.mark.django_db
def test_quote_for_pickup(client):
    response = post(client, method="pickup")
    assert response.status_code == 200 and response["Cache-Control"] == "no-store"
    assert response.json() == {
        "method": "pickup",
        "status": "priced",
        "fee": {"pesewas": 0, "display": "GHS 0.00"},
        "cod_allowed": False,
        "reason": None,
        "road_km": None,
    }


@pytest.mark.django_db
def test_quote_for_a_listed_and_an_unlisted_station(client, stations):
    listed = post(client, method="station", station_name="circle").json()
    assert listed["status"] == "priced" and listed["fee"]["pesewas"] == 1800
    unlisted = post(client, method="station", station_name="Tema Station 9").json()
    assert unlisted["status"] == "awaiting_quote" and unlisted["fee"] is None
    assert unlisted["reason"] == "unlisted_station"


@pytest.mark.django_db
def test_quote_for_a_doorstep_address(client, configured):
    near = post(client, method="doorstep", latitude=5.61, longitude=-0.19).json()
    assert near["status"] == "priced" and near["cod_allowed"] is True
    assert near["fee"]["pesewas"] >= 1500 and Decimal(near["road_km"]) > 0
    far = post(client, method="doorstep", latitude=6.6885, longitude=-1.6244).json()
    assert far["status"] == "awaiting_quote" and far["cod_allowed"] is False


@pytest.mark.django_db
def test_bad_quote_requests_are_validation_errors(client, configured):
    bad = [
        {},
        {"method": "drone"},
        {"method": "station"},
        {"method": "station", "station_name": "   "},
        {"method": "doorstep"},
        {"method": "doorstep", "latitude": 5.6},
        {"method": "doorstep", "latitude": 95, "longitude": 0},
        {"method": "doorstep", "latitude": 5.6, "longitude": 181},
        {"method": "doorstep", "latitude": "abc", "longitude": 0},
        {"method": "doorstep", "latitude": "nan", "longitude": 0},
        {"method": "doorstep", "latitude": "inf", "longitude": 0},
    ]
    for body in bad:
        response = post(client, **body)
        assert response.status_code == 400, body
        assert response.json()["error"]["code"] == "validation_error"


@pytest.mark.django_db
def test_a_client_can_never_name_its_own_fee(client, stations):
    for extra in ({"fee": 1}, {"fee_pesewas": 1}, {"price": 1}, {"cod_allowed": True}):
        response = post(client, method="pickup", **extra)
        assert response.status_code == 400, extra
    assert post(client, method="pickup").json()["fee"]["pesewas"] == 0


# --- the admin -------------------------------------------------------------------------


@pytest.mark.django_db
def test_delivery_admin_pages_load(admin_client, stations, configured):
    station = Station.objects.get(name="Circle")
    for url in (
        "/admin/delivery/station/",
        "/admin/delivery/station/add/",
        f"/admin/delivery/station/{station.pk}/change/",
        "/admin/delivery/deliverysettings/",
        "/admin/delivery/deliverysettings/1/change/",
    ):
        assert admin_client.get(url).status_code == 200, url


@pytest.mark.django_db
def test_staff_type_a_station_fee_in_cedis(admin_client):
    response = admin_client.post(
        "/admin/delivery/station/add/",
        {"name": "Tema  Station", "fee_ghs": "20.50", "is_active": "on"},
    )
    assert response.status_code == 302
    station = Station.objects.get(name="Tema Station")
    assert station.fee_pesewas == 2050
    refused = admin_client.post(
        "/admin/delivery/station/add/", {"name": "Bad", "fee_ghs": "20.505", "is_active": "on"}
    )
    assert refused.status_code == 200 and not Station.objects.filter(name="Bad").exists()


@pytest.mark.django_db
def test_a_duplicate_station_in_another_spelling_is_a_form_error_not_a_crash(admin_client):
    Station.objects.create(name="Circle", fee_pesewas=1800)
    response = admin_client.post(
        "/admin/delivery/station/add/",
        {"name": "  CIRCLE ", "fee_ghs": "5.00", "is_active": "on"},
    )
    assert response.status_code == 200
    assert Station.objects.count() == 1
    # editing a station and keeping its own name is fine
    station = Station.objects.get()
    kept = admin_client.post(
        f"/admin/delivery/station/{station.pk}/change/",
        {"name": "circle", "fee_ghs": "19.00", "is_active": "on"},
    )
    assert kept.status_code == 302
    station.refresh_from_db()
    assert (station.name, station.fee_pesewas) == ("circle", 1900)


@pytest.mark.django_db
def test_staff_fill_in_the_delivery_settings_once(admin_client):
    form = {
        "shop_latitude": "5.603700",
        "shop_longitude": "-0.187000",
        "minimum_fee_ghs": "15.00",
        "base_fee_ghs": "10.00",
        "rate_per_km_ghs": "2.00",
        "max_distance_km": "25.00",
        "road_factor": "1.30",
    }
    assert admin_client.post("/admin/delivery/deliverysettings/add/", form).status_code == 302
    saved = DeliverySettings.objects.get()
    assert (saved.minimum_fee_pesewas, saved.base_fee_pesewas, saved.rate_per_km_pesewas) == (
        1500,
        1000,
        200,
    )
    assert admin_client.get("/admin/delivery/deliverysettings/add/").status_code == 403


@pytest.mark.django_db
def test_nonsense_settings_are_form_errors_not_saved(admin_client):
    form = {
        "shop_latitude": "95",
        "shop_longitude": "-0.187",
        "minimum_fee_ghs": "15.00",
        "base_fee_ghs": "10.00",
        "rate_per_km_ghs": "2.00",
        "max_distance_km": "0",
        "road_factor": "1.30",
    }
    response = admin_client.post("/admin/delivery/deliverysettings/add/", form)
    assert response.status_code == 200 and not DeliverySettings.objects.exists()
