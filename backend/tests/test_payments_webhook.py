import json

import pytest

from apps.payments.models import PaystackWebhookEvent
from apps.payments.signature import compute_signature

SECRET = "sk_test_dummy_not_a_real_key"
URL = "/api/v1/payments/webhook/paystack/"


@pytest.fixture(autouse=True)
def paystack_secret(settings):
    settings.PAYSTACK_SECRET_KEY = SECRET


def _body(event="charge.success", reference="ref_1", amount=25000):
    payload = {
        "event": event,
        "data": {"reference": reference, "amount": amount, "currency": "GHS"},
    }
    return json.dumps(payload).encode()


def _post(client, body, signature=None):
    sig = compute_signature(body, SECRET) if signature is None else signature
    return client.post(
        URL, data=body, content_type="application/json", HTTP_X_PAYSTACK_SIGNATURE=sig
    )


@pytest.mark.django_db
def test_valid_webhook_is_recorded_once(client):
    response = _post(client, _body())
    assert response.status_code == 200
    assert response.json() == {"status": "received"}
    row = PaystackWebhookEvent.objects.get()
    assert (row.dedupe_key, row.amount, row.currency) == ("charge.success:ref_1", 25000, "GHS")


@pytest.mark.django_db
def test_replayed_three_times_is_recorded_once(client):
    body = _body()
    statuses = [_post(client, body).json()["status"] for _ in range(3)]
    assert statuses == ["received", "duplicate", "duplicate"]
    assert PaystackWebhookEvent.objects.count() == 1


@pytest.mark.django_db
def test_same_reference_different_event_is_a_new_event(client):
    _post(client, _body(event="charge.success"))
    _post(client, _body(event="charge.failed"))
    assert PaystackWebhookEvent.objects.count() == 2


@pytest.mark.django_db
def test_bad_signature_rejected_and_nothing_stored(client):
    response = _post(client, _body(), signature="0" * 128)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_signature"
    assert PaystackWebhookEvent.objects.count() == 0


@pytest.mark.django_db
def test_missing_signature_rejected(client):
    response = client.post(URL, data=_body(), content_type="application/json")
    assert response.status_code == 401
    assert PaystackWebhookEvent.objects.count() == 0


@pytest.mark.django_db
def test_body_changed_after_signing_rejected(client):
    sig = compute_signature(_body(amount=25000), SECRET)
    response = _post(client, _body(amount=1), signature=sig)
    assert response.status_code == 401
    assert PaystackWebhookEvent.objects.count() == 0


@pytest.mark.django_db
def test_no_secret_configured_rejects_everything(client, settings):
    settings.PAYSTACK_SECRET_KEY = ""
    body = _body()
    response = client.post(
        URL,
        data=body,
        content_type="application/json",
        HTTP_X_PAYSTACK_SIGNATURE=compute_signature(body, ""),
    )
    assert response.status_code == 401
    assert PaystackWebhookEvent.objects.count() == 0


@pytest.mark.django_db
def test_signed_but_invalid_json_is_400(client):
    assert _post(client, b"not json").status_code == 400


@pytest.mark.django_db
def test_signed_event_without_reference_is_ignored(client):
    body = json.dumps({"event": "charge.success", "data": {}}).encode()
    response = _post(client, body)
    assert response.status_code == 200
    assert response.json() == {"status": "ignored"}
    assert PaystackWebhookEvent.objects.count() == 0


def test_get_not_allowed(client):
    assert client.get(URL).status_code == 405
