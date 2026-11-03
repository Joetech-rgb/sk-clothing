import pytest
from django.core.cache import cache

from apps.orders.tests.conftest import checkout_environment, shop  # noqa: F401 (shared fixtures)
from apps.payments.client import reset_fake_paystack

SECRET = "sk_test_unit_secret"


@pytest.fixture(autouse=True)
def payment_environment(settings):
    settings.PAYSTACK_SECRET_KEY = SECRET
    settings.PAYSTACK_CLIENT = "fake"
    settings.PAYMENT_LIMITS = {"start_ip_rate": "10000/hour", "verify_ip_rate": "10000/hour"}
    settings.CSRF_TRUSTED_ORIGINS = ["https://www.example-shop.test"]
    cache.clear()
    reset_fake_paystack()
    yield
    cache.clear()
    reset_fake_paystack()
