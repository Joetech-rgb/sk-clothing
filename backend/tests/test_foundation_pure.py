import logging
import re

from hypothesis import given
from hypothesis import strategies as st

from config.client_ip import client_ip
from config.envelope import build_error, code_for_status, plain
from config.logging_filters import RedactingFilter, RequestIdFilter
from config.redaction import redact
from config.request_ids import (
    NO_REQUEST,
    get_request_id,
    new_request_id,
    reset_request_id,
    resolve_request_id,
    set_request_id,
)

# --- the error envelope ------------------------------------------------------------


def test_envelope_has_the_standard_shape():
    assert build_error("not_found", "Not found.") == {
        "error": {"code": "not_found", "message": "Not found."}
    }
    full = build_error(
        "validation_error", "Bad.", details={"phone": ["Invalid."]}, request_id="abc"
    )
    assert full == {
        "error": {
            "code": "validation_error",
            "message": "Bad.",
            "details": {"phone": ["Invalid."]},
            "request_id": "abc",
        }
    }


def test_empty_details_and_missing_request_id_are_left_out():
    error = build_error("x", "y", details={}, request_id=None)["error"]
    assert set(error) == {"code", "message"}


def test_status_codes_map_to_stable_error_codes():
    assert code_for_status(401) == "not_authenticated"
    assert code_for_status(403) == "permission_denied"
    assert code_for_status(404) == "not_found"
    assert code_for_status(429) == "throttled"
    assert code_for_status(500) == "server_error"
    assert code_for_status(503) == "server_error"
    assert code_for_status(418) == "error"


def test_plain_turns_string_subclasses_into_plain_json_types():
    class Detail(str):
        pass

    result = plain({"a": [Detail("x"), 1, None, True], "b": {"c": Detail("y")}})
    assert result == {"a": ["x", 1, None, True], "b": {"c": "y"}}
    assert type(result["a"][0]) is str


# --- request IDs ---------------------------------------------------------------------


def test_a_safe_incoming_id_is_kept_and_anything_else_is_replaced():
    assert resolve_request_id("abc12345-def_6.7") == "abc12345-def_6.7"
    hostile = (None, "", "short", "has space in it", "x" * 65, "bad\nnewline12", "semi;colon12345")
    for bad in hostile:
        replaced = resolve_request_id(bad)
        assert replaced != bad and re.fullmatch(r"[0-9a-f]{32}", replaced)


def test_new_ids_are_unique():
    assert len({new_request_id() for _ in range(1000)}) == 1000


def test_the_current_id_is_scoped_and_resets():
    assert get_request_id() == NO_REQUEST
    token = set_request_id("request-0001")
    assert get_request_id() == "request-0001"
    reset_request_id(token)
    assert get_request_id() == NO_REQUEST


# --- phone numbers stay out of logs -------------------------------------------------


def test_phone_numbers_in_every_spelling_are_masked():
    for number in (
        "+233241234567",
        "233241234567",
        "0241234567",
        "024 123 4567",
        "024-123-4567",
        "+233 24 123 4567",
    ):
        cleaned = redact(f"sent code to {number} now")
        assert "123" not in cleaned.replace("567", "") and number not in cleaned, number
        assert "[phone ***567]" in cleaned


def test_ordinary_text_and_numbers_are_left_alone():
    for text in ("order 4521 paid", "total GHS 12.50", "variant 101 qty 3", "request abc12345"):
        assert redact(text) == text


@given(digits=st.integers(min_value=100_000_000, max_value=999_999_999))
def test_no_nine_digit_ghana_number_survives_redaction(digits):
    for raw in (f"0{digits}", f"+233{digits}", f"233{digits}"):
        assert str(digits) not in redact(f"user {raw} logged in")


def test_log_records_are_stamped_and_masked():
    record = logging.LogRecord("t", logging.INFO, "f.py", 1, "hello %s", ("+233241234567",), None)
    token = set_request_id("request-0002")
    try:
        assert RequestIdFilter().filter(record) and record.request_id == "request-0002"
    finally:
        reset_request_id(token)
    assert RedactingFilter().filter(record)
    assert "233241234567" not in record.getMessage() and "***567" in record.getMessage()


def test_a_broken_log_call_does_not_raise():
    record = logging.LogRecord("t", logging.INFO, "f.py", 1, "needs %s and %s", ("one",), None)
    assert RedactingFilter().filter(record)


# --- who is calling --------------------------------------------------------------------


def test_the_cloudflare_header_is_ignored_unless_trusted():
    meta = {"REMOTE_ADDR": "10.0.0.5", "HTTP_CF_CONNECTING_IP": "203.0.113.9"}
    assert client_ip(meta, trust_cloudflare=False) == "10.0.0.5"  # cannot be spoofed
    assert client_ip(meta, trust_cloudflare=True) == "203.0.113.9"


def test_a_bad_forwarded_value_falls_back_to_the_connection_address():
    for bad in ("", "not-an-ip", "999.1.1.1", "1.2.3.4, 5.6.7.8"):
        meta = {"REMOTE_ADDR": "10.0.0.5", "HTTP_CF_CONNECTING_IP": bad}
        assert client_ip(meta, trust_cloudflare=True) == "10.0.0.5"


def test_ipv6_works_and_missing_data_is_unknown():
    meta = {"REMOTE_ADDR": "10.0.0.5", "HTTP_CF_CONNECTING_IP": "2001:db8::1"}
    assert client_ip(meta, trust_cloudflare=True) == "2001:db8::1"
    assert client_ip({}, trust_cloudflare=True) == "unknown"
    assert client_ip({"REMOTE_ADDR": "garbage"}, trust_cloudflare=False) == "unknown"
