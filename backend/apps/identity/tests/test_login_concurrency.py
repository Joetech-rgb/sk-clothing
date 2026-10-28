"""Simultaneous requests, on a real PostgreSQL database. These prove the guarantees that application
code alone cannot give: no extra guesses, no second use of a code, no second live code, no sending
past the daily cap, and no duplicate customer."""

import re
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import pytest
from django.contrib.auth import get_user_model
from django.db import connection, connections
from rest_framework.test import APIClient

from apps.identity import login
from apps.identity.models import LoginCode, SmsDailyCount

pytestmark = pytest.mark.django_db(transaction=True)

REQUEST = "/api/v1/auth/code/request/"
VERIFY = "/api/v1/auth/code/verify/"
PHONE = "0241234567"
User = get_user_model()


def number(n: int) -> str:
    return f"024123{n:04d}"


@pytest.fixture(autouse=True)
def generous_address_limits(settings):
    # every test request comes from one address; the address limits are not under test here
    settings.LOGIN_CODE_LIMITS = {"request_ip_rate": "10000/hour", "verify_ip_rate": "10000/hour"}


def in_parallel(count, work):
    """Run work(i) in `count` threads released at the same instant. Returns the results."""
    barrier = threading.Barrier(count)

    def run(i):
        try:
            barrier.wait(timeout=30)
            return work(i)
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=count) as pool:
        return list(pool.map(run, range(count)))


def issue(sms, phone=PHONE):
    assert APIClient().post(REQUEST, {"phone": phone}, format="json").status_code == 202
    return re.search(r"\b(\d{6})\b", sms.sent[-1][1]).group(1)


def verify(phone, code):
    return APIClient().post(VERIFY, {"phone": phone, "code": code}, format="json").status_code


def test_the_database_runs_postgresql():
    assert connection.vendor == "postgresql"


def test_simultaneous_wrong_guesses_are_still_limited_to_five(sms):
    real = issue(sms)
    wrong = "000000" if real != "000000" else "111111"
    statuses = Counter(in_parallel(30, lambda i: verify(PHONE, wrong)))
    assert statuses == {400: 5, 429: 25}
    assert LoginCode.objects.get().failed_attempts == 5
    assert verify(PHONE, real) == 429  # locked, even for the right code
    assert User.objects.count() == 0


def test_guessing_in_parallel_cannot_beat_the_limit_with_the_right_code_in_the_mix(sms):
    real = issue(sms)
    wrong = "000000" if real != "000000" else "111111"
    # 5 guesses are allowed; whichever gets there first wins, but never more than 5 attempts
    results = in_parallel(20, lambda i: verify(PHONE, real if i == 10 else wrong))
    row = LoginCode.objects.get()
    assert row.failed_attempts <= 5
    assert results.count(200) <= 1
    assert User.objects.count() == results.count(200)


def test_a_correct_code_can_be_used_by_only_one_of_many_simultaneous_requests(sms):
    real = issue(sms)
    statuses = Counter(in_parallel(15, lambda i: verify(PHONE, real)))
    assert statuses == {200: 1, 400: 14}
    assert User.objects.count() == 1
    assert LoginCode.objects.get().consumed is True


def test_simultaneous_requests_for_one_number_send_exactly_one_code(sms):
    statuses = Counter(
        in_parallel(
            25, lambda i: APIClient().post(REQUEST, {"phone": PHONE}, format="json").status_code
        )
    )
    assert statuses == {202: 1, 429: 24}
    assert len(sms.sent) == 1
    assert LoginCode.objects.filter(consumed=False, superseded=False).count() == 1
    assert LoginCode.objects.count() == 1
    assert SmsDailyCount.objects.get().count == 1


def test_the_daily_cap_cannot_be_exceeded_by_simultaneous_requests(sms, settings):
    settings.LOGIN_CODE_LIMITS = {
        "daily_sms_cap": 5,
        "request_ip_rate": "10000/hour",
        "verify_ip_rate": "10000/hour",
    }
    statuses = Counter(
        in_parallel(
            40,
            lambda i: APIClient().post(REQUEST, {"phone": number(i)}, format="json").status_code,
        )
    )
    assert statuses == {202: 5, 503: 35}
    assert SmsDailyCount.objects.get().count == 5
    assert len(sms.sent) == 5
    assert LoginCode.objects.count() == 5


def test_a_new_customer_created_by_simultaneous_requests_is_one_account():
    from apps.identity.phone import normalise_ghana_phone

    phone = normalise_ghana_phone(PHONE)
    results = in_parallel(12, lambda i: login._customer(phone))
    assert User.objects.count() == 1
    assert {user.pk for user, _ in results} == {User.objects.get().pk}
    assert [created for _, created in results].count(True) == 1


def test_simultaneous_first_logins_for_different_numbers_each_get_one_account(sms):
    codes = {n: issue(sms, number(n)) for n in range(8)}
    statuses = in_parallel(8, lambda i: verify(number(i), codes[i]))
    assert statuses == [200] * 8
    assert User.objects.count() == 8
