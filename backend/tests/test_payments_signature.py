from hypothesis import given
from hypothesis import strategies as st

from apps.payments.parsing import parse_event
from apps.payments.signature import compute_signature, verify_signature

SECRET = "sk_test_dummy_not_a_real_key"


def test_known_vector_matches_independent_hmac_sha512():
    # Produced independently with: printf 'hello' | openssl dgst -sha512 -hmac 'key'
    expected = (
        "ff06ab36757777815c008d32c8e14a705b4e7bf310351a06a23b612dc4c7433e"
        "7757d20525a5593b71020ea2ee162d2311b247e9855862b270122419652c0c92"
    )
    assert compute_signature(b"hello", "key") == expected


def test_valid_signature_accepted():
    body = b'{"event":"charge.success"}'
    assert verify_signature(body, compute_signature(body, SECRET), SECRET)


def test_wrong_secret_rejected():
    body = b'{"event":"charge.success"}'
    assert not verify_signature(body, compute_signature(body, "other"), SECRET)


def test_tampered_body_rejected():
    body = b'{"amount":1000}'
    sig = compute_signature(body, SECRET)
    assert not verify_signature(b'{"amount":9999}', sig, SECRET)


def test_missing_signature_or_secret_fails_closed():
    body = b"{}"
    assert not verify_signature(body, "", SECRET)
    assert not verify_signature(body, compute_signature(body, ""), "")


def test_non_ascii_signature_does_not_crash():
    assert not verify_signature(b"{}", "é" * 128, SECRET)


@given(body=st.binary(max_size=500), secret=st.text(min_size=1, max_size=40))
def test_roundtrip_always_verifies(body, secret):
    assert verify_signature(body, compute_signature(body, secret), secret)


@given(body=st.binary(min_size=1, max_size=500), secret=st.text(min_size=1, max_size=40))
def test_changing_one_byte_never_verifies(body, secret):
    sig = compute_signature(body, secret)
    changed = bytes([body[0] ^ 1]) + body[1:]
    assert not verify_signature(changed, sig, secret)


def test_parse_event_extracts_fields():
    payload = {
        "event": "charge.success",
        "data": {"reference": "ref_1", "amount": 25000, "currency": "GHS"},
    }
    event = parse_event(payload)
    assert event is not None
    assert (event.event_type, event.reference, event.amount, event.currency) == (
        "charge.success",
        "ref_1",
        25000,
        "GHS",
    )
    assert event.dedupe_key == "charge.success:ref_1"


def test_parse_event_rejects_bad_shapes():
    assert parse_event([]) is None
    assert parse_event({"event": "x"}) is None
    assert parse_event({"event": "x", "data": {}}) is None
    assert parse_event({"event": "x", "data": {"reference": ""}}) is None
    assert parse_event({"event": "x", "data": {"reference": "r" * 101}}) is None


def test_parse_event_never_treats_float_or_bool_as_amount():
    base = {"event": "e", "data": {"reference": "r"}}
    for bad in (10.5, True, "100", None):
        payload = {"event": "e", "data": {**base["data"], "amount": bad}}
        parsed = parse_event(payload)
        assert parsed is not None and parsed.amount is None
