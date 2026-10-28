"""The cookie and origin settings that staging and production must have (ADR 0016). These read
the settings modules directly, so a change that weakens them fails here."""

import importlib

import pytest

MODULES = ["config.settings.prod", "config.settings.staging"]


@pytest.fixture(params=MODULES)
def deployed(request, monkeypatch):
    monkeypatch.delenv("CSRF_TRUSTED_ORIGINS", raising=False)
    return importlib.reload(importlib.import_module(request.param))


def test_session_and_csrf_cookies_are_secure_and_not_readable_by_scripts(deployed):
    assert deployed.SESSION_COOKIE_SECURE is True
    assert deployed.SESSION_COOKIE_HTTPONLY is True
    assert deployed.CSRF_COOKIE_SECURE is True


def test_cookies_are_not_sent_on_cross_site_requests(deployed):
    assert deployed.SESSION_COOKIE_SAMESITE in ("Lax", "Strict")
    assert deployed.CSRF_COOKIE_SAMESITE in ("Lax", "Strict")


def test_the_site_knows_it_is_behind_an_https_proxy(deployed):
    assert deployed.SECURE_PROXY_SSL_HEADER == ("HTTP_X_FORWARDED_PROTO", "https")


def test_debug_is_off_and_the_fake_sms_provider_is_not_selected(deployed):
    assert deployed.DEBUG is False
    assert getattr(deployed, "SMS_PROVIDER", "") != "fake"


def test_trusted_origins_come_from_the_environment_and_keep_base_values(deployed, monkeypatch):
    monkeypatch.setenv("CSRF_TRUSTED_ORIGINS", " https://www.shop.test , https://shop.test,, ")
    reloaded = importlib.reload(deployed)
    assert "https://www.shop.test" in reloaded.CSRF_TRUSTED_ORIGINS
    assert "https://shop.test" in reloaded.CSRF_TRUSTED_ORIGINS
    assert "" not in reloaded.CSRF_TRUSTED_ORIGINS
    assert "https://already-in-base.example" in reloaded.CSRF_TRUSTED_ORIGINS


def test_without_the_environment_variable_no_extra_origin_is_trusted(deployed):
    assert deployed.CSRF_TRUSTED_ORIGINS == ["https://already-in-base.example"]
