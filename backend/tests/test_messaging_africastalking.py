import io
import json
import logging
import urllib.error
import urllib.parse
import urllib.request

import pytest

from apps.messaging import sms_africastalking as at
from apps.messaging.factory import ProviderNotConfigured, get_sms_provider

PHONE = "+233201234567"  # a made-up number
TEXT = "your code is 123456"
KEY = "test-api-key-not-real"


def answer(code, message_id="ATXid_test1"):
    body = {
        "SMSMessageData": {
            "Message": "Sent to 1/1",
            "Recipients": [
                {"statusCode": code, "number": PHONE, "status": "x", "messageId": message_id}
            ],
        }
    }
    return 200, json.dumps(body).encode()


class FakeResponse:
    def __init__(self, status, body):
        self.status = status
        self._body = body

    def read(self, limit=-1):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def provider(**kwargs):
    return at.AfricasTalkingSmsProvider("user1", KEY, **kwargs)


def reply(monkeypatch, status, body):
    """Make the HTTP layer answer with this, and remember the request that was sent."""
    seen = []

    def fake_urlopen(request, timeout=None):
        seen.append(request)
        if status >= 400:
            raise urllib.error.HTTPError(request.full_url, status, "x", {}, io.BytesIO(body))
        return FakeResponse(status, body)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return seen


def test_a_sent_message_is_accepted_and_keeps_the_provider_id(monkeypatch):
    reply(monkeypatch, *answer(101))
    result = provider().send(PHONE, TEXT, idempotency_key="k1")
    assert result.accepted and result.provider_id == "ATXid_test1" and result.error is None


@pytest.mark.parametrize("code", [100, 101, 102])
def test_processed_sent_and_queued_all_count_as_accepted(monkeypatch, code):
    reply(monkeypatch, *answer(code))
    assert provider().send(PHONE, TEXT, idempotency_key="k1").accepted


@pytest.mark.parametrize("code", [403, 404, 406, 409, 502])
def test_a_bad_or_blocked_number_is_not_retried(monkeypatch, code):
    reply(monkeypatch, *answer(code))
    result = provider().send(PHONE, TEXT, idempotency_key="k1")
    assert (result.accepted, result.retryable, result.error) == (False, False, f"at_status_{code}")


@pytest.mark.parametrize("code", [401, 402, 405, 407, 500, 501, 999])
def test_gateway_balance_sender_and_unknown_codes_are_retried(monkeypatch, code):
    reply(monkeypatch, *answer(code))
    result = provider().send(PHONE, TEXT, idempotency_key="k1")
    assert (result.accepted, result.retryable) == (False, True)


@pytest.mark.parametrize("status", [401, 403, 429, 500, 503])
def test_http_errors_that_can_clear_up_are_retried(monkeypatch, status):
    reply(monkeypatch, status, b"{}")
    result = provider().send(PHONE, TEXT, idempotency_key="k1")
    assert (result.accepted, result.retryable, result.error) == (False, True, f"at_http_{status}")


def test_a_malformed_request_is_not_retried(monkeypatch):
    reply(monkeypatch, 400, b"{}")
    result = provider().send(PHONE, TEXT, idempotency_key="k1")
    assert (result.accepted, result.retryable, result.error) == (False, False, "at_http_400")


@pytest.mark.parametrize(
    "body",
    [b"not json", b"[]", b'{"SMSMessageData": {}}', b'{"SMSMessageData": {"Recipients": []}}'],
)
def test_an_unusable_answer_is_retried(monkeypatch, body):
    reply(monkeypatch, 200, body)
    result = provider().send(PHONE, TEXT, idempotency_key="k1")
    assert (result.accepted, result.retryable) == (False, True)


def test_an_answer_with_no_status_code_is_retried(monkeypatch):
    body = {"SMSMessageData": {"Recipients": [{"number": PHONE}]}}
    reply(monkeypatch, 200, json.dumps(body).encode())
    result = provider().send(PHONE, TEXT, idempotency_key="k1")
    assert (result.accepted, result.retryable, result.error) == (False, True, "at_no_status")


def test_a_network_failure_is_retried(monkeypatch):
    def broken(request, timeout=None):
        raise urllib.error.URLError("no route")

    monkeypatch.setattr(urllib.request, "urlopen", broken)
    result = provider().send(PHONE, TEXT, idempotency_key="k1")
    assert (result.accepted, result.retryable, result.error) == (False, True, "at_unreachable")


def test_the_request_carries_the_key_in_a_header_and_not_in_the_body(monkeypatch):
    seen = reply(monkeypatch, *answer(101))
    provider(sender_id="SKCLOTHING").send(PHONE, TEXT, idempotency_key="k1")
    (request,) = seen
    fields = dict(urllib.parse.parse_qsl(request.data.decode()))
    assert request.full_url == at.LIVE_URL and request.get_method() == "POST"
    assert request.get_header("Apikey") == KEY and KEY not in request.data.decode()
    assert fields == {"username": "user1", "to": PHONE, "message": TEXT, "from": "SKCLOTHING"}


def test_without_a_sender_id_no_from_field_is_sent(monkeypatch):
    seen = reply(monkeypatch, *answer(101))
    provider().send(PHONE, TEXT, idempotency_key="k1")
    assert "from" not in dict(urllib.parse.parse_qsl(seen[0].data.decode()))


def test_the_sandbox_switch_uses_the_sandbox_address(monkeypatch):
    seen = reply(monkeypatch, *answer(101))
    provider(sandbox=True).send(PHONE, TEXT, idempotency_key="k1")
    assert seen[0].full_url == at.SANDBOX_URL


def test_failures_log_only_a_short_code_never_the_key_number_or_text(monkeypatch, caplog):
    reply(monkeypatch, *answer(405))
    with caplog.at_level(logging.DEBUG):
        provider().send(PHONE, TEXT, idempotency_key="k1")
    assert "at_status_405" in caplog.text
    assert KEY not in caplog.text and PHONE not in caplog.text and TEXT not in caplog.text


def test_build_needs_the_username_and_key(monkeypatch):
    monkeypatch.delenv("AT_USERNAME", raising=False)
    monkeypatch.delenv("AT_API_KEY", raising=False)
    with pytest.raises(ProviderNotConfigured):
        at.build()


def test_build_reads_the_environment(monkeypatch):
    monkeypatch.setenv("AT_USERNAME", "user1")
    monkeypatch.setenv("AT_API_KEY", KEY)
    monkeypatch.setenv("AT_SENDER_ID", "SKCLOTHING")
    monkeypatch.setenv("AT_SANDBOX", "1")
    built = at.build()
    assert built._url == at.SANDBOX_URL and built._sender_id == "SKCLOTHING"


def test_the_factory_builds_it_from_the_setting(settings, monkeypatch):
    settings.SMS_PROVIDER = "apps.messaging.sms_africastalking.build"
    monkeypatch.setenv("AT_USERNAME", "user1")
    monkeypatch.setenv("AT_API_KEY", KEY)
    assert isinstance(get_sms_provider(), at.AfricasTalkingSmsProvider)
