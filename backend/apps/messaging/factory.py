"""Chooses the SMS provider. Everything else asks here and talks to the SmsProvider interface.

SMS_PROVIDER (a setting) picks it:
- "fake": records messages instead of sending them. For tests and local work only.
- a dotted path such as "apps.messaging.sms_hubtel.build": a function returning a provider.
- unset: the fake in DEBUG, otherwise nothing, so staging and production refuse to send until a
  real provider is configured. Never set "fake" in production.
"""

from importlib import import_module

from django.conf import settings

from .providers import FakeSmsProvider, SmsProvider


class ProviderNotConfigured(RuntimeError):
    pass


_fake = FakeSmsProvider()


def fake_sms() -> FakeSmsProvider:
    """The shared fake, so tests can read what was 'sent'."""
    return _fake


def get_sms_provider() -> SmsProvider:
    name = getattr(settings, "SMS_PROVIDER", "")
    if name == "fake" or (not name and settings.DEBUG):
        return _fake
    if not name:
        raise ProviderNotConfigured("SMS_PROVIDER is not set")
    module, _, attribute = name.rpartition(".")
    if not module:
        raise ProviderNotConfigured(f"SMS_PROVIDER {name!r} is not a dotted path")
    return getattr(import_module(module), attribute)()
