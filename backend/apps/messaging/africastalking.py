"""Africa's Talking SMS provider.

It is not used until the provider factory is pointed at it with a setting. It needs no extra
library: it uses urllib from the standard library.

NOT verified. Check each of these against Africa's Talking's current documentation, and with a
run in their sandbox, before real sending is switched on:
- the status codes below (100, 101 and 102 count as accepted; the others are failures),
- that the live endpoint accepts our Ghana sender ID once it is approved,
- that Africa's Talking has no idempotency key. send() cannot pass one, so a retry after an
  unclear failure can send the same text twice. For our messages that costs a few pesewas and
  does no harm, so unclear failures are retried.

Never log the number, the text or the key.
"""

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any

from .providers import SendResult

LIVE_URL = "https://api.africastalking.com/version1/messaging"
SANDBOX_URL = "https://api.sandbox.africastalking.com/version1/messaging"
ACCEPTED = frozenset({100, 101, 102})  # processed, sent, queued
RETRYABLE = frozenset({407, 500, 501, 502})  # could not route, internal, gateway errors

# (url, headers, form body, timeout in seconds) -> (HTTP status, response text)
Transport = Callable[[str, dict[str, str], bytes, float], tuple[int, str]]


def urllib_transport(
    url: str, headers: dict[str, str], data: bytes, timeout: float
) -> tuple[int, str]:
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", "replace")


class AfricasTalkingProvider:
    def __init__(
        self,
        *,
        username: str,
        api_key: str,
        sender_id: str = "",
        sandbox: bool = False,
        transport: Transport | None = None,
        timeout: float = 15.0,
    ) -> None:
        self._username = username
        self._api_key = api_key
        self._sender_id = sender_id
        self._url = SANDBOX_URL if sandbox else LIVE_URL
        self._transport = transport or urllib_transport
        self._timeout = timeout

    def send(self, to_e164: str, text: str, *, idempotency_key: str = "") -> SendResult:
        del idempotency_key  # Africa's Talking has no such field (see the note at the top)
        fields = {"username": self._username, "to": to_e164, "message": text}
        if self._sender_id:
            fields["from"] = self._sender_id
        headers = {
            "apiKey": self._api_key,
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        try:
            status, body = self._transport(
                self._url, headers, urllib.parse.urlencode(fields).encode(), self._timeout
            )
        except OSError:  # no connection, reset, timeout
            return SendResult(accepted=False, error="network_error", retryable=True)

        if status >= 500:
            return SendResult(accepted=False, error=f"http_{status}", retryable=True)
        if status not in (200, 201):  # for example 400 or 401 (a wrong key): retrying will not help
            return SendResult(accepted=False, error=f"http_{status}", retryable=False)
        return self._read_answer(body)

    @staticmethod
    def _read_answer(body: str) -> SendResult:
        try:
            recipients = json.loads(body)["SMSMessageData"]["Recipients"]
            first: dict[str, Any] | None = recipients[0] if recipients else None
            code = int(first["statusCode"]) if first is not None else 0
        except (ValueError, KeyError, TypeError, IndexError):
            return SendResult(accepted=False, error="bad_response", retryable=True)
        if first is None:  # for example an invalid number: no recipient result at all
            return SendResult(accepted=False, error="no_recipient_result", retryable=False)
        if code in ACCEPTED:
            return SendResult(accepted=True, provider_id=str(first.get("messageId", "")))
        return SendResult(accepted=False, error=f"at_{code}", retryable=code in RETRYABLE)
