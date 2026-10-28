import logging
import re
from importlib import import_module

import pytest
from django.conf import settings as django_settings
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.identity import login, otp
from apps.identity.models import LoginCode, SmsDailyCount
from apps.messaging.providers import SendResult

pytestmark = pytest.mark.django_db

REQUEST = "/api/v1/auth/code/request/"
VERIFY = "/api/v1/auth/code/verify/"
PHONE = "0241234567"
E164 = "+233241234567"
User = get_user_model()


def session_exists(key):
    """Works with whichever session engine the project uses."""
    engine = import_module(django_settings.SESSION_ENGINE)
    return engine.SessionStore(session_key=key).exists(key)


def number(n: int) -> str:
    return f"024123{n:04d}"


def ask(client, phone=PHONE, **headers):
    return client.post(REQUEST, {"phone": phone}, format="json", **headers)


def send(client, code, phone=PHONE, **headers):
    return client.post(VERIFY, {"phone": phone, "code": code}, format="json", **headers)


def sent_code(sms, index=-1):
    return re.search(r"\b(\d{6})\b", sms.sent[index][1]).group(1)


def wrong_code(real):
    return "000000" if real != "000000" else "111111"


def reason(response):
    return response.json()["error"]["details"]["reason"]


def login_with_code(client, sms, phone=PHONE):
    assert ask(client, phone).status_code == 202
    return send(client, sent_code(sms), phone)


# --- the happy path ---------------------------------------------------------------------------


def test_request_sends_one_sms_and_stores_only_a_hash(sms):
    response = ask(APIClient())
    assert response.status_code == 202
    assert response.json() == {"expires_in_seconds": 300}
    assert len(sms.sent) == 1
    to, text = sms.sent[0]
    assert to == E164
    code = sent_code(sms)
    row = LoginCode.objects.get()
    assert row.code_hash == otp.hash_code(E164, code, login._key())
    assert code not in {row.phone, row.code_hash}
    assert row.failed_attempts == 0 and not row.consumed and not row.superseded


def test_verify_signs_the_customer_in_and_creates_the_account(sms):
    client = APIClient()
    response = login_with_code(client, sms)
    assert response.status_code == 200
    user = User.objects.get()
    assert response.json() == {"is_new_customer": True, "user": {"id": user.pk}}
    assert user.phone == E164 and user.email is None and not user.has_usable_password()
    assert not user.is_staff and not user.is_superuser
    assert client.session["_auth_user_id"] == str(user.pk)
    assert LoginCode.objects.get().consumed is True


def test_a_returning_customer_gets_the_same_account_whatever_the_spelling(sms, clock):
    client = APIClient()
    first = login_with_code(client, sms, PHONE).json()
    clock.advance(minutes=2)
    second = login_with_code(APIClient(), sms, "+233 24 123 4567").json()
    assert first["user"]["id"] == second["user"]["id"]
    assert (first["is_new_customer"], second["is_new_customer"]) == (True, False)
    assert User.objects.count() == 1


def test_login_responses_are_never_cached(sms):
    client = APIClient()
    assert ask(client)["Cache-Control"] == "no-store"
    assert send(client, sent_code(sms))["Cache-Control"] == "no-store"


def test_only_json_is_accepted(sms):
    response = APIClient().post(
        REQUEST, "phone=0241234567", content_type="application/x-www-form-urlencoded"
    )
    assert response.status_code == 415
    assert sms.sent == []


def test_a_bad_phone_number_is_a_validation_error(sms):
    response = ask(APIClient(), "12345")
    assert response.status_code == 400
    assert "phone" in response.json()["error"]["details"]
    assert sms.sent == [] and LoginCode.objects.count() == 0


# --- accounts are created only after a correct code -------------------------------------------


def test_no_account_exists_until_a_code_is_verified(sms):
    client = APIClient()
    ask(client)
    assert User.objects.count() == 0
    for _ in range(3):
        send(client, wrong_code(sent_code(sms)))
    assert User.objects.count() == 0
    send(client, sent_code(sms))
    assert User.objects.count() == 1


def test_a_second_account_for_the_same_number_is_refused_by_the_database():
    from django.db import IntegrityError, transaction

    User.objects.create_user(phone=PHONE)
    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.create_user(phone="+233 24 123 4567")


def test_the_database_refuses_two_live_codes_for_one_number():
    from datetime import timedelta

    from django.db import IntegrityError, transaction
    from django.utils import timezone

    def row(**extra):
        return LoginCode(
            phone=E164, code_hash="x", expires_at=timezone.now() + timedelta(minutes=5), **extra
        )

    row().save()
    with pytest.raises(IntegrityError), transaction.atomic():
        row().save()
    row(consumed=True).save()  # used and retired codes may pile up
    row(superseded=True).save()
    assert LoginCode.objects.filter(phone=E164).count() == 3


def test_the_database_keeps_one_counter_row_per_day():
    from datetime import date

    from django.db import IntegrityError, transaction

    SmsDailyCount.objects.create(day=date(2026, 10, 27))
    with pytest.raises(IntegrityError), transaction.atomic():
        SmsDailyCount.objects.create(day=date(2026, 10, 27))


# --- sessions ---------------------------------------------------------------------------------


def test_the_session_key_changes_at_sign_in_and_the_old_one_dies(sms):
    client = APIClient()
    planted = client.session
    planted["planted"] = "by an attacker"
    planted.save()
    old_key = planted.session_key
    assert login_with_code(client, sms).status_code == 200
    new_key = client.session.session_key
    assert new_key != old_key
    assert not session_exists(old_key)
    assert session_exists(new_key)


def test_signing_in_replaces_another_users_session_on_the_same_browser(sms):
    other = User.objects.create_user(email="ama@example.com", password="pw-12345-xyz")
    client = APIClient()
    client.force_login(other)
    old_key = client.session.session_key
    assert login_with_code(client, sms).status_code == 200
    assert client.session["_auth_user_id"] != str(other.pk)
    assert client.session.session_key != old_key
    assert not session_exists(old_key)


def test_a_failed_login_starts_no_session(sms):
    client = APIClient()
    ask(client)
    assert send(client, wrong_code(sent_code(sms))).status_code == 400
    assert "_auth_user_id" not in client.session


# --- wrong, expired, reused and malformed codes ----------------------------------------------


def test_five_wrong_guesses_lock_the_code_even_against_the_right_one(sms):
    client = APIClient()
    ask(client)
    real = sent_code(sms)
    for _ in range(5):
        response = send(client, wrong_code(real))
        assert response.status_code == 400 and reason(response) == "invalid_code"
    assert LoginCode.objects.get().failed_attempts == 5
    locked = send(client, real)
    assert locked.status_code == 429 and reason(locked) == "too_many_attempts"
    assert send(client, wrong_code(real)).status_code == 429
    assert LoginCode.objects.get().failed_attempts == 5  # locked codes are not counted further
    assert User.objects.count() == 0


def test_a_code_is_valid_just_before_expiry_and_dead_at_expiry(sms, clock):
    client = APIClient()
    ask(client)
    real = sent_code(sms)
    clock.advance(minutes=4, seconds=59)
    assert send(client, real).status_code == 200
    # a second code, left until exactly its expiry moment
    clock.advance(minutes=2)
    ask(APIClient())
    second = sent_code(sms)
    clock.advance(minutes=5)
    response = send(APIClient(), second)
    assert response.status_code == 400 and reason(response) == "invalid_code"


def test_a_correct_code_works_once_so_replaying_it_fails(sms):
    client = APIClient()
    ask(client)
    real = sent_code(sms)
    assert send(client, real).status_code == 200
    replay = send(APIClient(), real)
    assert replay.status_code == 400 and reason(replay) == "invalid_code"
    assert User.objects.count() == 1


def test_malformed_codes_are_refused_without_using_up_a_guess(sms):
    client = APIClient()
    ask(client)
    for junk in ("12", "abcdef", "1234567", "", "12 34"):
        assert send(client, junk).status_code in (400,)
    assert LoginCode.objects.get().failed_attempts == 0
    assert send(client, sent_code(sms)).status_code == 200


def test_a_code_for_a_number_with_no_request_is_refused(sms):
    response = send(APIClient(), "123456")
    assert response.status_code == 400 and reason(response) == "invalid_code"
    assert User.objects.count() == 0


def test_a_new_code_retires_the_old_one(sms, clock):
    client = APIClient()
    ask(client)
    first = sent_code(sms)
    clock.advance(seconds=61)
    ask(client)
    second = sent_code(sms)
    assert first and second
    assert LoginCode.objects.filter(superseded=False, consumed=False).count() == 1
    assert LoginCode.objects.filter(superseded=True).count() == 1
    assert send(client, second).status_code == 200


# --- staff and switched-off accounts ---------------------------------------------------------


def test_a_staff_number_gets_the_same_answer_but_no_code(sms):
    User.objects.create_user(email="boss@example.com", phone=PHONE, is_staff=True)
    response = ask(APIClient())
    assert response.status_code == 202 and response.json() == {"expires_in_seconds": 300}
    assert sms.sent == [] and LoginCode.objects.count() == 0
    assert SmsDailyCount.objects.count() == 0


def test_a_code_cannot_sign_a_staff_or_switched_off_account_in(sms):
    for n, flags in enumerate(({"is_staff": True}, {"is_superuser": True}, {"is_active": False})):
        phone = number(n)
        User.objects.create_user(email=f"u{n}@example.com", phone=phone, **flags)
        code, record = otp.issue_otp(phone, now=login._now(), key=login._key())
        normalised = User.objects.get(email=f"u{n}@example.com").phone
        LoginCode.objects.create(
            phone=normalised,
            code_hash=otp.hash_code(normalised, code, login._key()),
            expires_at=record.expires_at,
        )
        client = APIClient()
        response = send(client, code, phone)
        assert response.status_code == 400 and reason(response) == "invalid_code"
        assert "_auth_user_id" not in client.session


def test_unknown_and_known_customers_get_identical_answers(sms):
    User.objects.create_user(phone=number(1))
    known = ask(APIClient(), number(1))
    unknown = ask(APIClient(), number(2))
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()


# --- limits: one code per minute, five per hour -----------------------------------------------


def test_a_second_request_within_a_minute_is_refused_and_costs_nothing(sms, clock):
    client = APIClient()
    assert ask(client).status_code == 202
    clock.advance(seconds=20)
    response = ask(client)
    assert response.status_code == 429
    assert response.json()["error"]["details"]["retry_after_seconds"] == 40
    assert len(sms.sent) == 1
    assert SmsDailyCount.objects.get().count == 1


def test_five_codes_an_hour_per_number_then_the_window_slides(sms, clock):
    client = APIClient()
    for _ in range(5):
        assert ask(client).status_code == 202
        clock.advance(seconds=61)
    sixth = ask(client)
    assert sixth.status_code == 429
    assert sixth.json()["error"]["details"]["retry_after_seconds"] == 3600 - 5 * 61
    assert len(sms.sent) == 5
    clock.advance(seconds=3600 - 5 * 61)
    assert ask(client).status_code == 202


def test_one_number_does_not_limit_another(sms):
    assert ask(APIClient(), number(1)).status_code == 202
    assert ask(APIClient(), number(2)).status_code == 202


def test_requests_per_address_are_limited(sms, settings):
    settings.LOGIN_CODE_LIMITS = {"request_ip_rate": "3/hour"}
    client = APIClient()
    assert [ask(client, number(n)).status_code for n in range(4)] == [202, 202, 202, 429]
    assert len(sms.sent) == 3


def test_verify_attempts_per_address_are_limited(sms, settings):
    settings.LOGIN_CODE_LIMITS = {"verify_ip_rate": "2/hour"}
    client = APIClient()
    ask(client)
    real = sent_code(sms)
    assert send(client, wrong_code(real)).status_code == 400
    assert send(client, wrong_code(real)).status_code == 400
    limited = send(client, real)
    assert (
        limited.status_code == 429 and "retry_after_seconds" in limited.json()["error"]["details"]
    )
    assert LoginCode.objects.get().failed_attempts == 2


# --- the daily SMS cap -----------------------------------------------------------------------


def test_the_daily_cap_stops_sending_and_resets_the_next_day(sms, settings, clock):
    settings.LOGIN_CODE_LIMITS = {"daily_sms_cap": 3}
    codes = [ask(APIClient(), number(n)).status_code for n in range(4)]
    assert codes == [202, 202, 202, 503]
    refused = ask(APIClient(), number(3))
    assert refused.status_code == 503 and reason(refused) == "sms_unavailable"
    assert len(sms.sent) == 3
    assert SmsDailyCount.objects.get().count == 3
    assert LoginCode.objects.count() == 3  # a refused request leaves no code behind
    clock.advance(days=1)
    assert ask(APIClient(), number(3)).status_code == 202
    assert sorted(SmsDailyCount.objects.values_list("count", flat=True)) == [1, 3]


def test_a_refused_request_does_not_use_up_the_allowance(sms, settings, clock):
    settings.LOGIN_CODE_LIMITS = {"daily_sms_cap": 2}
    ask(APIClient())
    ask(APIClient())  # too soon: refused
    assert SmsDailyCount.objects.get().count == 1
    assert ask(APIClient(), number(1)).status_code == 202
    assert SmsDailyCount.objects.get().count == 2


# --- provider problems ------------------------------------------------------------------------


def reject_everything():
    class Rejecting:
        def send(self, to_e164, text, *, idempotency_key):
            return SendResult(accepted=False, error="down", retryable=True)

    return Rejecting()


def test_no_configured_provider_refuses_to_send(sms, settings):
    settings.SMS_PROVIDER = ""
    response = ask(APIClient())
    assert response.status_code == 503 and reason(response) == "sms_unavailable"
    assert LoginCode.objects.count() == 0 and SmsDailyCount.objects.count() == 0


def test_the_fake_provider_is_not_used_implicitly_outside_debug(sms, settings):
    settings.SMS_PROVIDER = ""
    settings.DEBUG = False
    assert ask(APIClient()).status_code == 503
    assert sms.sent == []


def test_a_provider_that_rejects_the_message_gives_a_clean_error(sms, settings):
    settings.SMS_PROVIDER = "apps.identity.tests.test_login.reject_everything"
    response = ask(APIClient())
    assert response.status_code == 503 and reason(response) == "sms_unavailable"


# --- login-CSRF: the Origin check -------------------------------------------------------------


@pytest.mark.parametrize("origin", ["https://evil.example", "null", "http://www.example-shop.test"])
def test_requests_from_untrusted_origins_do_nothing(sms, origin):
    client = APIClient()
    refused = ask(client, HTTP_ORIGIN=origin)
    assert refused.status_code == 403 and reason(refused) == "bad_origin"
    assert sms.sent == [] and LoginCode.objects.count() == 0
    assert SmsDailyCount.objects.count() == 0


def test_a_cross_site_post_cannot_sign_a_visitor_in_even_with_the_right_code(sms):
    client = APIClient()
    ask(client)
    real = sent_code(sms)
    refused = send(client, real, HTTP_ORIGIN="https://evil.example")
    assert refused.status_code == 403
    assert "_auth_user_id" not in client.session
    row = LoginCode.objects.get()
    assert not row.consumed and row.failed_attempts == 0
    assert send(client, real).status_code == 200  # the real site can still use it


@pytest.mark.parametrize("origin", ["https://www.example-shop.test", "http://testserver"])
def test_trusted_origins_are_accepted(sms, origin):
    assert ask(APIClient(), HTTP_ORIGIN=origin).status_code == 202


def test_a_browser_marked_cross_site_without_an_origin_is_refused(sms):
    response = ask(APIClient(), HTTP_SEC_FETCH_SITE="cross-site")
    assert response.status_code == 403 and sms.sent == []


@pytest.mark.parametrize("site", ["same-origin", "same-site", "none"])
def test_other_fetch_metadata_values_are_allowed(sms, site, clock):
    assert ask(APIClient(), HTTP_SEC_FETCH_SITE=site).status_code == 202


def test_callers_that_send_no_origin_headers_are_allowed(sms):
    assert ask(APIClient()).status_code == 202


# --- nothing sensitive reaches the logs -------------------------------------------------------


def test_codes_hashes_and_full_numbers_never_reach_the_logs(sms, caplog, clock):
    caplog.set_level(logging.DEBUG)
    client = APIClient()
    ask(client)
    real = sent_code(sms)
    send(client, wrong_code(real))
    send(client, real)
    ask(APIClient(), "0249999999")
    text = "\n".join(f"{r.getMessage()} {r.args}" for r in caplog.records)
    row_hash = otp.hash_code(E164, real, login._key())
    for secret in (real, row_hash, E164, PHONE, "241234567", "249999999"):
        assert secret not in text
    assert "+233" in text  # a masked number is logged, so there is something to look at


def test_login_objects_do_not_print_numbers_or_hashes(sms):
    ask(APIClient())
    row = LoginCode.objects.get()
    for text in (str(row), repr(row)):
        assert row.phone not in text and row.code_hash not in text
