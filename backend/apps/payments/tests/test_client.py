"""The real Paystack client, against a small fake of Paystack's server running on this machine."""

import json
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from apps.payments.client import (
    FakePaystack,
    PaystackError,
    PaystackHttpClient,
    ProviderNotConfigured,
    get_paystack_client,
)

SECRET = "sk_live_super_secret_value"


class Handler(BaseHTTPRequestHandler):
    def _answer(self):
        server = self.server
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        server.requests.append(
            {
                "method": self.command,
                "path": self.path,
                "auth": self.headers.get("Authorization"),
                "content_type": self.headers.get("Content-Type"),
                "body": json.loads(body) if body else None,
            }
        )
        status, payload = server.next_response
        if server.delay:
            time.sleep(server.delay)
        raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    do_GET = do_POST = _answer

    def log_message(self, *args):
        pass


@pytest.fixture
def paystack():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.requests = []
    server.next_response = (200, {})
    server.delay = 0
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    server.client = PaystackHttpClient(
        SECRET, base_url=f"http://127.0.0.1:{server.server_address[1]}", timeout=0.5
    )
    yield server
    server.shutdown()
    server.server_close()


def ok(data):
    return 200, {"status": True, "message": "ok", "data": data}


def test_initialize_sends_what_paystack_expects_and_reads_the_answer(paystack):
    paystack.next_response = ok(
        {
            "authorization_url": "https://checkout.paystack.com/abc",
            "access_code": "abc",
            "reference": "SK123-aa",
        }
    )
    result = paystack.client.initialize(
        email="ama@example.com",
        amount_pesewas=12550,
        reference="SK123-aa",
        callback_url="https://shop.test/paid",
    )
    assert (result.authorization_url, result.access_code, result.reference) == (
        "https://checkout.paystack.com/abc",
        "abc",
        "SK123-aa",
    )
    (request,) = paystack.requests
    assert request["method"] == "POST" and request["path"] == "/transaction/initialize"
    assert request["auth"] == f"Bearer {SECRET}" and request["content_type"] == "application/json"
    assert request["body"] == {
        "email": "ama@example.com",
        "amount": 12550,
        "currency": "GHS",
        "reference": "SK123-aa",
        "callback_url": "https://shop.test/paid",
    }
    assert isinstance(request["body"]["amount"], int)


def test_initialize_leaves_out_the_callback_when_there_is_none(paystack):
    paystack.next_response = ok(
        {
            "authorization_url": "https://checkout.paystack.com/a",
            "access_code": "a",
            "reference": "r",
        }
    )
    paystack.client.initialize(email="a@b.co", amount_pesewas=1, reference="r")
    assert "callback_url" not in paystack.requests[0]["body"]


def test_verify_reads_status_amount_and_currency(paystack):
    paystack.next_response = ok(
        {"status": "success", "amount": 12550, "currency": "GHS", "reference": "SK123-aa"}
    )
    result = paystack.client.verify("SK123-aa")
    assert (result.status, result.amount, result.currency, result.reference) == (
        "success",
        12550,
        "GHS",
        "SK123-aa",
    )
    assert paystack.requests[0]["method"] == "GET"
    assert paystack.requests[0]["path"] == "/transaction/verify/SK123-aa"


def test_a_reference_is_made_safe_for_the_url(paystack):
    paystack.next_response = ok(
        {"status": "failed", "amount": 1, "currency": "GHS", "reference": "x"}
    )
    paystack.client.verify("a/b?c=d e")
    assert paystack.requests[0]["path"] == "/transaction/verify/a%2Fb%3Fc%3Dd%20e"


@pytest.mark.parametrize("amount", [None, "12550", 125.5, True])
def test_an_amount_that_is_not_whole_pesewas_reads_as_unknown(paystack, amount):
    paystack.next_response = ok(
        {"status": "success", "amount": amount, "currency": "GHS", "reference": "r"}
    )
    assert paystack.client.verify("r").amount is None


@pytest.mark.parametrize("status", [500, 502, 503, 429])
def test_outages_and_rate_limits_are_worth_retrying(paystack, status):
    paystack.next_response = (status, {"status": False, "message": "later"})
    with pytest.raises(PaystackError) as caught:
        paystack.client.verify("r")
    assert caught.value.retryable is True


@pytest.mark.parametrize("status", [400, 401, 403, 404])
def test_refusals_are_not_worth_retrying(paystack, status):
    paystack.next_response = (status, {"status": False, "message": "no"})
    with pytest.raises(PaystackError) as caught:
        paystack.client.verify("r")
    assert caught.value.retryable is False


def test_a_200_that_says_status_false_is_a_refusal(paystack):
    paystack.next_response = (200, {"status": False, "message": "Invalid key"})
    with pytest.raises(PaystackError) as caught:
        paystack.client.verify("r")
    assert caught.value.retryable is False


@pytest.mark.parametrize(
    "payload",
    [b"<html>bad gateway</html>", b"", b"[1, 2]", {"status": True}, {"status": True, "data": "x"}],
)
def test_unreadable_or_unexpected_answers_are_worth_retrying(paystack, payload):
    paystack.next_response = (200, payload)
    with pytest.raises(PaystackError) as caught:
        paystack.client.verify("r")
    assert caught.value.retryable is True


@pytest.mark.parametrize("url", ["http://evil.example/pay", "javascript:alert(1)", "", None])
def test_a_payment_page_that_is_not_https_is_refused(paystack, url):
    paystack.next_response = ok({"authorization_url": url, "access_code": "a", "reference": "r"})
    with pytest.raises(PaystackError):
        paystack.client.initialize(email="a@b.co", amount_pesewas=1, reference="r")


def test_a_slow_paystack_times_out_and_can_be_retried(paystack):
    paystack.delay = 1.5
    paystack.next_response = ok(
        {"status": "success", "amount": 1, "currency": "GHS", "reference": "r"}
    )
    started = time.monotonic()
    with pytest.raises(PaystackError) as caught:
        paystack.client.verify("r")
    assert caught.value.retryable is True and time.monotonic() - started < 1.4


def test_an_unreachable_paystack_can_be_retried():
    client = PaystackHttpClient(SECRET, base_url="http://127.0.0.1:9", timeout=0.5)
    with pytest.raises(PaystackError) as caught:
        client.verify("r")
    assert caught.value.retryable is True


def test_errors_and_logs_never_contain_the_key_the_answer_or_the_email(paystack, caplog):
    caplog.set_level(logging.DEBUG)
    paystack.next_response = (
        400,
        {"status": False, "message": "ama@example.com card 4084084084084081"},
    )
    with pytest.raises(PaystackError) as caught:
        paystack.client.initialize(email="ama@example.com", amount_pesewas=1, reference="r")
    text = str(caught.value) + "\n".join(r.getMessage() for r in caplog.records)
    for secret in (SECRET, "ama@example.com", "4084084084084081"):
        assert secret not in text


# --- choosing the client ---------------------------------------------------------------------


def test_the_fake_is_used_when_asked_for(settings):
    settings.PAYSTACK_CLIENT = "fake"
    assert isinstance(get_paystack_client(), FakePaystack)


def test_the_real_client_is_used_when_there_is_a_key(settings):
    settings.PAYSTACK_CLIENT = ""
    settings.PAYSTACK_SECRET_KEY = "sk_test_x"
    assert isinstance(get_paystack_client(), PaystackHttpClient)


def test_no_key_means_no_client(settings):
    settings.PAYSTACK_CLIENT = ""
    settings.PAYSTACK_SECRET_KEY = ""
    with pytest.raises(ProviderNotConfigured):
        get_paystack_client()


@pytest.mark.parametrize("module", ["config.settings.prod", "config.settings.staging"])
def test_the_fake_is_refused_under_staging_and_production(settings, monkeypatch, module):
    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", module)
    settings.PAYSTACK_CLIENT = "fake"
    with pytest.raises(ProviderNotConfigured):
        get_paystack_client()
