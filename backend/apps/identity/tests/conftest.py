from datetime import UTC, datetime, timedelta

import pytest
from django.core.cache import cache

from apps.identity import login
from apps.messaging.factory import fake_sms


class Clock:
    """A clock the test controls. Install it with the `clock` fixture."""

    def __init__(self) -> None:
        self.now = datetime(2026, 10, 27, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs: float) -> None:
        self.now += timedelta(**kwargs)


@pytest.fixture(autouse=True)
def login_environment(settings):
    settings.SMS_PROVIDER = "fake"
    settings.LOGIN_CODE_LIMITS = {}
    settings.CSRF_TRUSTED_ORIGINS = ["https://www.example-shop.test"]
    cache.clear()
    fake = fake_sms()
    fake.sent.clear()
    fake._seen.clear()
    yield fake
    cache.clear()


@pytest.fixture
def sms(login_environment):
    return login_environment


@pytest.fixture
def clock(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(login, "_now", clock)
    return clock
