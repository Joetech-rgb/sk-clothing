"""The Africa's Talking SMS provider. Standard library only: no SDK, no new dependency.

Endpoint, header and fields are from Africa's Talking's own documentation (SMS, Sending): a POST
to /version1/messaging (live, or the sandbox host), the API key in an `apiKey` header, and the
fields username, to, message and optionally from (the sender id). The answer lists each
recipient with a statusCode, which says the message was accepted, not that it was delivered.
If no sender id is given, Africa's Talking uses its default one.

Africa's Talking has no idempotency key, so the key we are given cannot stop a second send. The
outbox keeps that rare (a message is only put back after a worker has been stuck for minutes).

Which status codes are permanent and which are worth retrying is our reading: it comes from a
third-party table, not from Africa's Talking's page, so confirm it against the official table
before real sending is switched on (docs/PROGRESS.md).

Settings, from the environment: AT_USERNAME, AT_API_KEY, AT_SENDER_ID (optional), AT_SANDBOX
("1" for the sandbox). Select it with SMS_PROVIDER=apps.messaging.sms_africastalking.build.

Never log the API key, a message, or a phone number. Only short error codes are logged.
"""

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request

from .factory import ProviderNotConfigured
from .providers import SendResult

logger = logging.getLogger(__name__)

LIVE_URL = "https://api.africastalking.com/version1/messaging"
SANDBOX_URL = "https://api.sandbox.africastalking.com/version1/messaging"
MAX_RESPONSE_BYTES = 1_000_000

# Recipient status codes meaning the message was taken (processed, sent or queued).
ACCEPTED_CODES = frozenset({100, 101, 102})
# Codes where trying again cannot help: bad or unsupported number, blocked, do-not-disturb,
# rejected by the gateway. Every other code is retried a few times, because a gateway fault,
# no balance or an unapproved sender id can be fixed while the message waits.
PERMANENT_CODES = frozenset({403, 404, 406, 409, 502})
# HTTP answers worth retrying: bad credentials or rate limiting (fixable), and any server error.
RETRYABLE_HTTP = frozenset({401, 403, 429})


class _Unreachable(Exception):
    pass


class AfricasTalkingSmsProvider:
    def __init__(
        self,
        username: str,
        api_key: str,
        *,
        sender_id: str = "",
        sandbox: bool = False,
        timeout: float = 10.0,
    ) -> None:
        self._username = username
        self._api_key = api_key
        self._sender_id = sender_id
        self._url = SANDBOX_URL if sandbox else LIVE_URL
        self._timeout = timeout

    def _post(self, fields: dict[str, str]) -> tuple[int, bytes]:
        request = urllib.request.Request(
            self._url,
            data=urllib.parse.urlencode(fields).encode(),
            method="POST",
            headers={
                "apiKey": self._api_key,
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                return response.status, response.read(MAX_RESPONSE_BYTES)
        except urllib.error.HTTPError as error:
            return error.code, error.read(MAX_RESPONSE_BYTES)
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise _Unreachable from error

    def send(self, to_e164: str, text: str, *, idempotency_key: str) -> SendResult:
        fields = {"username": self._username, "to": to_e164, "message": text}
        if self._sender_id:
            fields["from"] = self._sender_id
        try:
            status, raw = self._post(fields)
        except _Unreachable:
            return self._failed("at_unreachable", retryable=True)
        if status >= 400:
            retryable = status >= 500 or status in RETRYABLE_HTTP
            return self._failed(f"at_http_{status}", retryable=retryable)
        try:
            payload = json.loads(raw)
        except ValueError:
            return self._failed("at_unreadable", retryable=True)
        data = payload.get("SMSMessageData") if isinstance(payload, dict) else None
        recipients = data.get("Recipients") if isinstance(data, dict) else None
        first = recipients[0] if isinstance(recipients, list) and recipients else None
        if not isinstance(first, dict):
            return self._failed("at_no_recipient", retryable=True)
        code = first.get("statusCode")
        if isinstance(code, bool) or not isinstance(code, int):
            return self._failed("at_no_status", retryable=True)
        if code in ACCEPTED_CODES:
            return SendResult(accepted=True, provider_id=str(first.get("messageId") or "")[:64])
        return self._failed(f"at_status_{code}", retryable=code not in PERMANENT_CODES)

    @staticmethod
    def _failed(error: str, *, retryable: bool) -> SendResult:
        logger.warning("africa's talking did not take a message (%s)", error)
        return SendResult(accepted=False, error=error, retryable=retryable)


def build() -> AfricasTalkingSmsProvider:
    username = os.environ.get("AT_USERNAME", "")
    api_key = os.environ.get("AT_API_KEY", "")
    if not username or not api_key:
        raise ProviderNotConfigured("AT_USERNAME and AT_API_KEY must be set")
    return AfricasTalkingSmsProvider(
        username,
        api_key,
        sender_id=os.environ.get("AT_SENDER_ID", ""),
        sandbox=os.environ.get("AT_SANDBOX", "") == "1",
    )
