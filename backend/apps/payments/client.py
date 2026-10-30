"""Talking to Paystack. Everything else uses the PaystackClient interface, so the rest of the
system is tested with a fake and never needs the network.

Paystack's rules, from its documentation: amounts are whole pesewas for GHS; the page a customer
returns to proves nothing, so a payment counts only after `transaction/verify` says `success`
and the amount matches.

Never log the secret key, a response body or an email address.
"""

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Protocol

from django.conf import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://api.paystack.co"
MAX_RESPONSE_BYTES = 1_000_000


class PaystackError(Exception):
    """A call to Paystack did not give a usable answer. `retryable` says if trying again later
    may help (network trouble, a Paystack outage, rate limiting)."""

    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


class ProviderNotConfigured(RuntimeError):
    pass


@dataclass(frozen=True)
class InitResult:
    authorization_url: str
    access_code: str
    reference: str


@dataclass(frozen=True)
class VerifyResult:
    status: str  # Paystack's word: success, failed, abandoned, pending, ...
    amount: int | None  # whole pesewas
    currency: str
    reference: str


class PaystackClient(Protocol):
    def initialize(
        self, *, email: str, amount_pesewas: int, reference: str, callback_url: str | None = None
    ) -> InitResult: ...

    def verify(self, reference: str) -> VerifyResult: ...


@dataclass
class FakePaystack:
    """Stands in for Paystack in tests and local work. Records what was asked, and answers
    `verify` from what `initialize` was given unless a test says otherwise."""

    initialized: dict[str, dict] = field(default_factory=dict)
    outcomes: dict[str, "VerifyResult | Exception"] = field(default_factory=dict)
    verify_calls: list[str] = field(default_factory=list)
    fail_initialize: Exception | None = None

    def initialize(
        self, *, email: str, amount_pesewas: int, reference: str, callback_url: str | None = None
    ) -> InitResult:
        if self.fail_initialize is not None:
            raise self.fail_initialize
        self.initialized[reference] = {
            "email": email,
            "amount": amount_pesewas,
            "callback_url": callback_url,
        }
        return InitResult(f"https://checkout.example/{reference}", f"ac_{reference}", reference)

    def set_outcome(
        self,
        reference: str,
        *,
        status: str = "success",
        amount: int | None = None,
        currency: str = "GHS",
    ) -> None:
        if amount is None:
            amount = self.initialized[reference]["amount"]
        self.outcomes[reference] = VerifyResult(status, amount, currency, reference)

    def fail_verify(self, reference: str, error: Exception) -> None:
        self.outcomes[reference] = error

    def verify(self, reference: str) -> VerifyResult:
        self.verify_calls.append(reference)
        outcome = self.outcomes.get(reference)
        if isinstance(outcome, Exception):
            raise outcome
        if outcome is not None:
            return outcome
        if reference not in self.initialized:
            raise PaystackError("transaction not found", retryable=False)
        return VerifyResult("success", self.initialized[reference]["amount"], "GHS", reference)


_fake = FakePaystack()


def fake_paystack() -> FakePaystack:
    return _fake


def reset_fake_paystack() -> None:
    _fake.initialized.clear()
    _fake.outcomes.clear()
    _fake.verify_calls.clear()
    _fake.fail_initialize = None


class PaystackHttpClient:
    """The real client, using only the standard library (no new dependency)."""

    def __init__(self, secret_key: str, *, base_url: str = BASE_URL, timeout: float = 10.0) -> None:
        self._secret_key = secret_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def _call(self, method: str, path: str, body: dict | None = None) -> dict:
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(
            self._base_url + path,
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self._secret_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                status, raw = response.status, response.read(MAX_RESPONSE_BYTES)
        except urllib.error.HTTPError as error:
            status, raw = error.code, error.read(MAX_RESPONSE_BYTES)
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise PaystackError("could not reach Paystack", retryable=True) from error
        retryable = status >= 500 or status == 429
        try:
            payload = json.loads(raw)
        except ValueError as error:
            raise PaystackError(
                f"Paystack sent unreadable data ({status})", retryable=True
            ) from error
        if not isinstance(payload, dict):
            raise PaystackError(
                f"Paystack sent an unexpected answer ({status})",
                retryable=retryable or status < 400,
            )
        if status >= 400 or payload.get("status") is not True:
            raise PaystackError(f"Paystack refused the request ({status})", retryable=retryable)
        result = payload.get("data")
        if not isinstance(result, dict):
            raise PaystackError("Paystack sent an unexpected answer", retryable=True)
        return result

    def initialize(
        self, *, email: str, amount_pesewas: int, reference: str, callback_url: str | None = None
    ) -> InitResult:
        body = {
            "email": email,
            "amount": amount_pesewas,
            "currency": "GHS",
            "reference": reference,
        }
        if callback_url:
            body["callback_url"] = callback_url
        data = self._call("POST", "/transaction/initialize", body)
        url, code = data.get("authorization_url"), data.get("access_code")
        if not isinstance(url, str) or not url.startswith("https://") or not isinstance(code, str):
            raise PaystackError("Paystack sent an unexpected answer", retryable=True)
        return InitResult(url, code, str(data.get("reference") or reference))

    def verify(self, reference: str) -> VerifyResult:
        data = self._call("GET", f"/transaction/verify/{urllib.parse.quote(reference, safe='')}")
        amount = data.get("amount")
        if isinstance(amount, bool) or not isinstance(amount, int):
            amount = None
        return VerifyResult(
            status=str(data.get("status") or ""),
            amount=amount,
            currency=str(data.get("currency") or ""),
            reference=str(data.get("reference") or ""),
        )


def _deployed() -> bool:
    return os.environ.get("DJANGO_SETTINGS_MODULE", "").endswith((".prod", ".staging"))


def get_paystack_client() -> PaystackClient:
    """PAYSTACK_CLIENT="fake" gives the fake, for tests and local work. It is refused under the
    staging and production settings. Otherwise the real client, which needs PAYSTACK_SECRET_KEY."""
    if getattr(settings, "PAYSTACK_CLIENT", "") == "fake":
        if _deployed():
            raise ProviderNotConfigured("the fake Paystack client cannot be used when deployed")
        return _fake
    if not settings.PAYSTACK_SECRET_KEY:
        raise ProviderNotConfigured("PAYSTACK_SECRET_KEY is not set")
    return PaystackHttpClient(settings.PAYSTACK_SECRET_KEY)
