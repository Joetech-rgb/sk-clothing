"""A successful code check that carries no user id must be refused and start no session.

This guard was added to make the type check pass (PROGRESS.md, deviations awaiting approval). It
cannot happen with the real login code today, so the check is replaced by one that returns an
"ok" result with no user id.
"""

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.identity import login

ORIGIN = "https://www.example-shop.test"  # the trusted origin set in this folder's conftest


@pytest.mark.django_db
def test_a_successful_check_with_no_user_id_is_refused_and_starts_no_session(monkeypatch):
    monkeypatch.setattr(
        login, "verify_code", lambda *args, **kwargs: login.VerifyResult(login.OK, None)
    )
    client = APIClient()
    response = client.post(
        reverse("auth-code-verify"),
        {"phone": "0201234567", "code": "123456"},
        format="json",
        HTTP_ORIGIN=ORIGIN,
    )
    assert response.status_code == 400
    assert client.session.get("_auth_user_id") is None
