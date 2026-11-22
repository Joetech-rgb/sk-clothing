import json
import urllib.parse

from apps.messaging import africastalking as at

NUMBER = "+233201234567"
TEXT = "S.K Clothing: order SK-ABCDEFGH was received."


def answer(code, message_id="ATPid_123"):
    recipient = {"statusCode": code, "number": NUMBER, "status": "x", "messageId": message_id}
    return json.dumps({"SMSMessageData": {"Message": "Sent to 1/1", "Recipients": [recipient]}})


def provider(status, body, calls=None, **options):
    def transport(url, headers, data, timeout):
        if calls is not None:
            calls.append((url, headers, urllib.parse.parse_qs(data.decode()), timeout))
        if isinstance(status, Exception):
            raise status
        return status, body

    return at.AfricasTalkingProvider(username="demo", api_key="key", transport=transport, **options)


def test_a_sent_message_is_accepted_with_its_id():
    result = provider(201, answer(101)).send(NUMBER, TEXT)
    assert result.accepted and result.provider_id == "ATPid_123"


def test_processed_and_queued_also_count_as_accepted():
    assert provider(201, answer(100)).send(NUMBER, TEXT).accepted
    assert provider(201, answer(102)).send(NUMBER, TEXT).accepted


def test_the_request_carries_the_account_key_number_and_text():
    calls = []
    provider(201, answer(101), calls).send(NUMBER, TEXT, idempotency_key="k-1")
    url, headers, form, _ = calls[0]
    assert url == at.LIVE_URL
    assert headers["apiKey"] == "key"
    assert form["username"] == ["demo"] and form["to"] == [NUMBER] and form["message"] == [TEXT]
    assert "from" not in form
    assert "k-1" not in str(form)  # no idempotency field exists


def test_a_sender_id_is_sent_when_set_and_sandbox_uses_the_sandbox_address():
    calls = []
    provider(201, answer(101), calls, sender_id="SKCLOTHING", sandbox=True).send(NUMBER, TEXT)
    url, _, form, _ = calls[0]
    assert url == at.SANDBOX_URL
    assert form["from"] == ["SKCLOTHING"]


def test_a_bad_number_is_a_permanent_failure():
    result = provider(201, answer(403)).send(NUMBER, TEXT)
    assert not result.accepted and not result.retryable and result.error == "at_403"


def test_a_gateway_error_is_retried():
    result = provider(201, answer(502)).send(NUMBER, TEXT)
    assert not result.accepted and result.retryable and result.error == "at_502"


def test_an_invalid_number_with_no_recipient_result_is_permanent():
    body = json.dumps({"SMSMessageData": {"Message": "InvalidPhoneNumber", "Recipients": []}})
    result = provider(201, body).send(NUMBER, TEXT)
    assert not result.accepted and not result.retryable and result.error == "no_recipient_result"


def test_a_server_error_is_retried_and_a_wrong_key_is_not():
    server = provider(503, "unavailable").send(NUMBER, TEXT)
    assert not server.accepted and server.retryable and server.error == "http_503"
    key = provider(401, "The supplied authentication is invalid").send(NUMBER, TEXT)
    assert not key.accepted and not key.retryable and key.error == "http_401"


def test_a_dropped_connection_is_retried():
    result = provider(ConnectionResetError(), "").send(NUMBER, TEXT)
    assert not result.accepted and result.retryable and result.error == "network_error"


def test_an_unreadable_answer_is_retried():
    for body in ("not json", "{}", json.dumps({"SMSMessageData": {"Recipients": [{}]}})):
        result = provider(201, body).send(NUMBER, TEXT)
        assert not result.accepted and result.retryable and result.error == "bad_response"


def test_errors_never_contain_the_number_or_the_text():
    for status, body in ((201, answer(403)), (503, "x"), (401, "x")):
        error = provider(status, body).send(NUMBER, TEXT).error
        assert NUMBER not in error and TEXT not in error
