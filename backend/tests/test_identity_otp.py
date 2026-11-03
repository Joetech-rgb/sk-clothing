import re
from datetime import datetime, timedelta, timezone

import pytest

from apps.identity.otp import (
    EXPIRED,
    LOCKED,
    MALFORMED,
    MAX_FAILED_ATTEMPTS,
    OK,
    TTL,
    USED,
    WRONG,
    OtpRecord,
    check_otp,
    hash_code,
    issue_otp,
)

KEY = b"test-key-not-a-real-secret"
PHONE = "+233241234567"
NOW = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)


def issue():
    return issue_otp(PHONE, now=NOW, key=KEY)


def wrong(code):
    return "000000" if code != "000000" else "111111"


def test_a_code_is_six_digits_valid_for_five_minutes_and_stored_hashed():
    code, record = issue()
    assert re.fullmatch(r"[0-9]{6}", code)
    assert TTL == timedelta(minutes=5) and record.expires_at == NOW + TTL
    assert code not in repr(record) and PHONE not in repr(record)
    assert record.code_hash == hash_code(PHONE, code, KEY) and code not in record.code_hash


def test_the_right_code_works_once():
    code, record = issue()
    record, result = check_otp(record, code, now=NOW + timedelta(seconds=30), key=KEY)
    assert result == OK and record.consumed
    assert check_otp(record, code, now=NOW + timedelta(seconds=40), key=KEY)[1] == USED


def test_the_expiry_boundary():
    code, record = issue()
    last_moment = NOW + TTL - timedelta(seconds=1)
    assert check_otp(record, code, now=last_moment, key=KEY)[1] == OK
    assert check_otp(record, code, now=NOW + TTL, key=KEY)[1] == EXPIRED
    assert check_otp(record, code, now=NOW + TTL + timedelta(hours=1), key=KEY)[1] == EXPIRED


def test_five_wrong_guesses_lock_it_even_for_the_right_code():
    code, record = issue()
    for attempt in range(1, MAX_FAILED_ATTEMPTS + 1):
        record, result = check_otp(record, wrong(code), now=NOW, key=KEY)
        assert result == WRONG and record.failed_attempts == attempt
    assert check_otp(record, code, now=NOW, key=KEY)[1] == LOCKED


def test_malformed_input_is_not_a_guess():
    code, record = issue()
    for junk in ("", "12345", "1234567", "12ab56", "１２３４５６"):
        new_record, result = check_otp(record, junk, now=NOW, key=KEY)
        assert result == MALFORMED and new_record == record


def test_a_code_only_works_for_the_number_it_was_sent_to():
    code, record = issue()
    other = OtpRecord("+233201111111", record.code_hash, record.expires_at)
    assert check_otp(other, code, now=NOW, key=KEY)[1] == WRONG


def test_a_code_does_not_work_under_another_key():
    code, record = issue()
    assert check_otp(record, code, now=NOW, key=b"another")[1] == WRONG


def test_times_must_carry_a_time_zone():
    with pytest.raises(ValueError):
        issue_otp(PHONE, now=datetime(2026, 11, 20, 12, 0), key=KEY)
    code, record = issue()
    with pytest.raises(ValueError):
        check_otp(record, code, now=datetime(2026, 11, 20, 12, 0), key=KEY)


def test_new_codes_are_different_each_time():
    codes = {issue()[0] for _ in range(200)}
    assert len(codes) > 150
