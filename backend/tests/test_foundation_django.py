import re

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse
from django.test import RequestFactory
from rest_framework.exceptions import NotAuthenticated, Throttled, ValidationError
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView

from config import views
from config.api_errors import api_exception_handler, not_found, server_error
from config.middleware import RequestIdMiddleware
from config.request_ids import NO_REQUEST, get_request_id
from config.throttling import AnonThrottle


def test_users_are_the_custom_identity_model(settings):
    assert settings.AUTH_USER_MODEL == "identity.User"
    assert get_user_model()._meta.label == "identity.User"


# --- request IDs ------------------------------------------------------------------


def test_every_response_carries_a_request_id_and_the_view_can_see_it():
    middleware = RequestIdMiddleware(lambda request: HttpResponse(get_request_id()))
    response = middleware(RequestFactory().get("/"))
    request_id = response["X-Request-ID"]
    assert re.fullmatch(r"[0-9a-f]{32}", request_id)
    assert response.content.decode() == request_id
    assert get_request_id() == NO_REQUEST  # cleared afterwards


def test_a_safe_id_from_the_caller_is_kept_and_a_hostile_one_is_replaced():
    middleware = RequestIdMiddleware(lambda request: HttpResponse("ok"))
    kept = middleware(RequestFactory().get("/", HTTP_X_REQUEST_ID="trace-12345678"))
    assert kept["X-Request-ID"] == "trace-12345678"
    replaced = middleware(RequestFactory().get("/", HTTP_X_REQUEST_ID="x y\tz;drop"))
    assert re.fullmatch(r"[0-9a-f]{32}", replaced["X-Request-ID"])


# --- the error envelope -------------------------------------------------------------


def error_of(exc):
    response = api_exception_handler(exc, {})
    return response.status_code, response.data["error"]


def test_validation_errors_list_the_fields():
    status, error = error_of(ValidationError({"phone": ["Enter a valid number."]}))
    assert status == 400
    assert error["code"] == "validation_error"
    assert error["details"] == {"phone": ["Enter a valid number."]}


def test_authentication_permission_and_not_found_errors():
    assert error_of(NotAuthenticated())[1]["code"] == "not_authenticated"
    assert error_of(PermissionDenied())[0] == 403
    assert error_of(PermissionDenied())[1]["code"] == "permission_denied"
    assert error_of(Http404())[0] == 404 and error_of(Http404())[1]["code"] == "not_found"


def test_throttled_errors_say_how_long_to_wait():
    status, error = error_of(Throttled(wait=4.2))
    assert status == 429 and error["code"] == "throttled"
    assert error["details"] == {"retry_after_seconds": 5}


def test_errors_that_are_not_api_errors_are_left_to_the_500_handler():
    assert api_exception_handler(ValueError("boom"), {}) is None


def test_the_500_and_404_pages_are_json_in_the_same_envelope():
    import json

    pages = ((server_error, 500, "server_error"), (not_found, 404, "not_found"))
    for handler, status, code in pages:
        response = handler(RequestFactory().get("/"))
        assert response.status_code == status
        assert json.loads(response.content)["error"]["code"] == code


def test_an_unknown_url_answers_in_the_envelope(client):
    response = client.get("/api/v1/nothing-here/")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


# --- secure by default ------------------------------------------------------------------


class Probe(APIView):
    def get(self, request):
        return Response({"ok": True})


def test_an_api_view_is_private_unless_it_says_otherwise():
    response = Probe.as_view()(APIRequestFactory().get("/"))
    assert response.status_code == 401  # 401, not 403, so the storefront can show a login screen
    assert response.data["error"]["code"] == "not_authenticated"
    assert response["WWW-Authenticate"] == "Session"


def test_basic_auth_is_not_accepted():
    import base64

    token = base64.b64encode(b"admin@example.com:password").decode()
    request = APIRequestFactory().get("/", HTTP_AUTHORIZATION=f"Basic {token}")
    assert Probe.as_view()(request).status_code == 401


# --- throttling uses the real caller ------------------------------------------------------


def test_throttle_identifies_the_caller_by_the_trusted_header_only(settings):
    request = APIRequestFactory().get(
        "/", REMOTE_ADDR="10.0.0.5", HTTP_CF_CONNECTING_IP="203.0.113.9"
    )
    settings.TRUST_CLOUDFLARE_HEADERS = False
    assert AnonThrottle().get_ident(request) == "10.0.0.5"
    settings.TRUST_CLOUDFLARE_HEADERS = True
    assert AnonThrottle().get_ident(request) == "203.0.113.9"


# --- health ------------------------------------------------------------------------------


def test_liveness_is_cheap(client):
    assert client.get("/api/v1/health/").json() == {"status": "ok"}


@pytest.mark.django_db
def test_readiness_reports_each_check(client, settings):
    settings.READINESS_CHECKS = ("database",)
    response = client.get("/api/v1/health/ready/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {"database": "ok"}}


@pytest.mark.django_db
def test_readiness_fails_with_503_when_a_dependency_is_down(client, settings, monkeypatch):
    settings.READINESS_CHECKS = ("database",)

    def down():
        raise ConnectionError("database is down")

    monkeypatch.setitem(views.CHECKS, "database", down)
    response = client.get("/api/v1/health/ready/")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "checks": {"database": "failed"}}
    assert "database is down" not in response.content.decode()  # no internal detail leaks
