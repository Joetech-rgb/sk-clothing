import logging
from datetime import timedelta

import pytest
from django.conf import settings as django_settings
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.identity import login
from apps.identity.models import LoginCode, SmsDailyCount
from apps.identity.tests.test_login import (
    E164,
    PHONE,
    ask,
    login_with_code,
    number,
    reason,
    session_exists,
)

pytestmark = pytest.mark.django_db

LOGOUT = "/api/v1/auth/logout/"
ME = "/api/v1/auth/me/"
User = get_user_model()


# --- the allowance kept for existing customers ------------------------------------------------


def test_made_up_numbers_cannot_use_the_part_of_the_allowance_kept_for_customers(sms, settings):
    settings.LOGIN_CODE_LIMITS = {"daily_sms_cap": 5, "daily_sms_reserved_for_customers": 2}
    flood = [ask(APIClient(), number(n)).status_code for n in range(6)]
    assert flood == [202, 202, 202, 503, 503, 503]
    customers = [User.objects.create_user(phone=number(900 + n)).phone for n in range(3)]
    answers = [ask(APIClient(), phone).status_code for phone in customers]
    assert answers == [202, 202, 503]  # the two reserved messages, then the true cap
    assert SmsDailyCount.objects.get().count == 5
    assert len(sms.sent) == 5


def test_a_reserve_larger_than_the_cap_leaves_it_all_to_customers(sms, settings):
    settings.LOGIN_CODE_LIMITS = {"daily_sms_cap": 2, "daily_sms_reserved_for_customers": 9}
    assert ask(APIClient(), number(1)).status_code == 503
    phone = User.objects.create_user(phone=number(2)).phone
    assert ask(APIClient(), phone).status_code == 202


def test_a_staff_number_never_uses_the_allowance(sms, settings):
    settings.LOGIN_CODE_LIMITS = {"daily_sms_cap": 3, "daily_sms_reserved_for_customers": 0}
    User.objects.create_user(email="boss@example.com", phone=PHONE, is_staff=True)
    for _ in range(5):
        assert ask(APIClient()).status_code == 202
    assert SmsDailyCount.objects.count() == 0


# --- alerts -----------------------------------------------------------------------------------


def alerts(caplog):
    records = [r for r in caplog.records if r.name == "apps.identity.login"]
    warnings = [r for r in records if r.levelno == logging.WARNING and "80%" in r.getMessage()]
    errors = [r for r in records if r.levelno == logging.ERROR]
    return warnings, errors


def test_an_alert_is_logged_at_eighty_percent_and_an_error_when_the_allowance_runs_out(
    sms, settings, caplog
):
    settings.LOGIN_CODE_LIMITS = {"daily_sms_cap": 10, "daily_sms_reserved_for_customers": 0}
    caplog.set_level(logging.INFO)
    for n in range(13):
        ask(APIClient(), number(n))
    warnings, errors = alerts(caplog)
    assert len(warnings) == 1 and "8 of 10" in warnings[0].getMessage()
    assert len(errors) == 1 and "used up" in errors[0].getMessage()


def test_each_allowance_raises_its_own_error(sms, settings, caplog):
    settings.LOGIN_CODE_LIMITS = {"daily_sms_cap": 4, "daily_sms_reserved_for_customers": 2}
    caplog.set_level(logging.INFO)
    for n in range(4):
        ask(APIClient(), number(n))  # new numbers: 2 allowed
    for n in range(3):
        ask(APIClient(), User.objects.create_user(phone=number(900 + n)).phone)
    _, errors = alerts(caplog)
    assert [("new numbers" in e.getMessage()) for e in errors] == [True, False]
    assert "customers" in errors[1].getMessage()


def test_alerts_contain_no_phone_numbers(sms, settings, caplog):
    settings.LOGIN_CODE_LIMITS = {"daily_sms_cap": 10, "daily_sms_reserved_for_customers": 0}
    caplog.set_level(logging.INFO)
    for n in range(12):
        ask(APIClient(), number(n))
    text = "\n".join(r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING)
    assert "24123" not in text and "+233" not in text


# --- who am I, and logout ---------------------------------------------------------------------


def test_nobody_signed_in_gets_401_from_me():
    response = APIClient().get(ME)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"


def test_me_describes_the_signed_in_customer_and_is_never_cached(sms):
    client = APIClient()
    login_with_code(client, sms)
    response = client.get(ME)
    assert response.status_code == 200
    assert response["Cache-Control"] == "no-store"
    user = User.objects.get()
    assert response.json() == {
        "id": user.pk,
        "full_name": "",
        "phone": E164,
        "email": None,
        "is_staff": False,
    }


def test_logout_ends_the_session_and_the_old_cookie_stops_working(sms):
    client = APIClient()
    login_with_code(client, sms)
    old_key = client.session.session_key
    response = client.post(LOGOUT, {}, format="json")
    assert response.status_code == 204 and response.content == b""
    assert response["Cache-Control"] == "no-store"
    assert not session_exists(old_key)
    assert client.get(ME).status_code == 401
    replay = APIClient()
    replay.cookies[django_settings.SESSION_COOKIE_NAME] = old_key
    assert replay.get(ME).status_code == 401


def test_logout_with_nobody_signed_in_is_not_an_error():
    assert APIClient().post(LOGOUT, {}, format="json").status_code == 204


def test_a_cross_site_page_cannot_sign_a_visitor_out(sms):
    client = APIClient()
    login_with_code(client, sms)
    refused = client.post(LOGOUT, {}, format="json", HTTP_ORIGIN="https://evil.example")
    assert refused.status_code == 403 and reason(refused) == "bad_origin"
    assert client.get(ME).status_code == 200


def test_logout_only_accepts_post(sms):
    client = APIClient()
    login_with_code(client, sms)
    assert client.get(LOGOUT).status_code == 405
    assert client.get(ME).status_code == 200


# --- clearing out old codes -------------------------------------------------------------------


def make_codes(now, ages_in_days):
    for n, days in enumerate(ages_in_days):
        LoginCode.objects.create(
            phone=f"+23324123{n:04d}",
            code_hash="x",
            expires_at=now,
            created_at=now - timedelta(days=days),
            consumed=True,
        )


def test_codes_older_than_a_week_are_deleted_and_newer_ones_kept(clock):
    make_codes(clock.now, [1, 6, 8, 9, 30, 60])
    assert login.purge_old_login_codes(now=clock.now, batch_size=2) == 4
    assert sorted(
        round((clock.now - c.created_at).total_seconds() / 86400) for c in LoginCode.objects.all()
    ) == [1, 6]


def test_the_cutoff_is_exactly_seven_days(clock):
    make_codes(clock.now, [7])
    assert login.purge_old_login_codes(now=clock.now) == 0
    clock.advance(seconds=1)
    assert login.purge_old_login_codes(now=clock.now) == 1


def test_clearing_codes_leaves_the_daily_sms_counts_alone(clock):
    make_codes(clock.now, [30])
    SmsDailyCount.objects.create(day=(clock.now - timedelta(days=200)).date(), count=7)
    login.purge_old_login_codes(now=clock.now)
    assert SmsDailyCount.objects.get().count == 7


def test_clearing_with_nothing_to_clear_is_fine():
    assert login.purge_old_login_codes() == 0


def test_the_scheduled_task_clears_old_codes_and_reports_how_many():
    from django.utils import timezone

    from apps.identity.tasks import purge_old_login_codes

    make_codes(timezone.now(), [10, 20, 1])
    assert purge_old_login_codes() == 2
    assert LoginCode.objects.count() == 1


# --- the fake SMS provider can never run on a live site ---------------------------------------


@pytest.mark.parametrize("module", ["config.settings.prod", "config.settings.staging"])
@pytest.mark.parametrize("setting", ["fake", ""])
def test_the_fake_provider_is_refused_under_staging_and_production(
    sms, settings, monkeypatch, module, setting
):
    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", module)
    settings.SMS_PROVIDER = setting
    settings.DEBUG = True  # even a stray DEBUG cannot bring it back
    response = ask(APIClient())
    assert response.status_code == 503 and reason(response) == "sms_unavailable"
    assert sms.sent == [] and LoginCode.objects.count() == 0


def test_the_fake_provider_still_works_under_other_settings(sms, monkeypatch):
    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "config.settings.local")
    assert ask(APIClient()).status_code == 202
    assert len(sms.sent) == 1
