"""Interfaces for sending messages, so the SMS and email providers can be chosen later.

The brief names these as allowed extension points (CLAUDE.md section 6). Real providers are chosen
by the client (the SMS quotes are pending; email is Resend or Brevo). Everything else in the system
talks to these interfaces only.

Sending uses an idempotency key, so a retried job never sends a second message. Implementations
must never log message bodies or full phone numbers.
"""

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class SendResult:
    accepted: bool
    provider_id: str | None = None
    error: str | None = None
    retryable: bool = False  # True: try again later. False: do not retry.


class SmsProvider(Protocol):
    def send(self, to_e164: str, text: str, *, idempotency_key: str) -> SendResult: ...


class EmailProvider(Protocol):
    def send(
        self, to: str, subject: str, text: str, *, html: str | None = None, idempotency_key: str
    ) -> SendResult: ...


@dataclass
class FakeSmsProvider:
    """Records messages instead of sending them. For tests and local development."""

    sent: list[tuple[str, str]] = field(default_factory=list)
    _seen: dict[str, SendResult] = field(default_factory=dict)

    def send(self, to_e164: str, text: str, *, idempotency_key: str) -> SendResult:
        if idempotency_key in self._seen:
            return self._seen[idempotency_key]
        self.sent.append((to_e164, text))
        result = SendResult(accepted=True, provider_id=f"fake-sms-{len(self.sent)}")
        self._seen[idempotency_key] = result
        return result


@dataclass
class FakeEmailProvider:
    sent: list[tuple[str, str, str]] = field(default_factory=list)
    _seen: dict[str, SendResult] = field(default_factory=dict)

    def send(
        self, to: str, subject: str, text: str, *, html: str | None = None, idempotency_key: str
    ) -> SendResult:
        if idempotency_key in self._seen:
            return self._seen[idempotency_key]
        self.sent.append((to, subject, text))
        result = SendResult(accepted=True, provider_id=f"fake-email-{len(self.sent)}")
        self._seen[idempotency_key] = result
        return result
