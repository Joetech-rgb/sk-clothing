"""Outbox services. Other apps call queue_sms(), never the outbox model directly.

Delivery is at least once, made safe by the idempotency key: a message is queued once per key,
claimed by one worker at a time, and the key is passed to the provider on every attempt. If a
worker dies after the provider accepted a message but before we recorded it, the reaper puts the
message back and it is sent again. Whether the provider drops a repeated key must be confirmed in
its documentation before real sending is switched on.

Never log a recipient, a body or a key. Log the message id and the exception class only.
"""

import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .factory import get_sms_provider
from .models import OutboxMessage
from .providers import SendResult

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 6
STUCK_AFTER = timedelta(minutes=10)
BATCH_SIZE = 100

SKIPPED = "skipped"


def backoff(attempts: int) -> timedelta:
    """Wait before the next try: 1 minute, then 2, 4, 8, and never more than an hour."""
    return timedelta(seconds=min(60 * 2 ** (attempts - 1), 3600))


def queue_sms(
    *,
    to_e164: str,
    text: str,
    template: str,
    idempotency_key: str,
    enqueue: bool = True,
) -> tuple[OutboxMessage, bool]:
    """Queue an SMS. Returns (message, created). Queuing the same key again changes nothing.

    Call this inside the transaction that caused the message. The send task is scheduled only
    after that transaction commits, so a rolled-back event sends nothing.
    """
    if not idempotency_key:
        raise ValueError("an idempotency key is required")
    message, created = OutboxMessage.objects.get_or_create(
        idempotency_key=idempotency_key,
        defaults={"channel": "sms", "recipient": to_e164, "template": template, "body": text},
    )
    if created and enqueue:
        message_id = message.pk
        transaction.on_commit(lambda: _enqueue(message_id))
    return message, created


def _enqueue(message_id: int) -> None:
    """Ask Celery to send now. If that fails the periodic sweep sends it later."""
    from .tasks import send_outbox_message

    try:
        send_outbox_message.delay(message_id)
    except Exception as exc:
        logger.warning("could not enqueue outbox message %s (%s)", message_id, type(exc).__name__)


def deliver(message_id: int) -> str:
    """Try to send one message. Returns the resulting status, or SKIPPED if it was not due or
    another worker already has it."""
    now = timezone.now()
    with transaction.atomic():
        message = (
            OutboxMessage.objects.select_for_update(skip_locked=True)
            .filter(pk=message_id, status=OutboxMessage.Status.PENDING, next_attempt_at__lte=now)
            .first()
        )
        if message is None:
            return SKIPPED
        message.status = OutboxMessage.Status.SENDING
        message.claimed_at = now
        message.attempts += 1
        message.save(update_fields=["status", "claimed_at", "attempts"])

    if message.channel != "sms":
        return _finish(message, SendResult(accepted=False, error="unsupported_channel"))
    try:
        result = get_sms_provider().send(
            message.recipient, message.body, idempotency_key=message.idempotency_key
        )
    except Exception as exc:  # a provider bug or a missing setting must not lose the message
        logger.warning("sms send raised %s for outbox message %s", type(exc).__name__, message.pk)
        result = SendResult(accepted=False, error="provider_exception", retryable=True)
    return _finish(message, result)


def _finish(message: OutboxMessage, result: SendResult) -> str:
    """Record the outcome. Only touches the row if this worker still owns it (status sending)."""
    now = timezone.now()
    if result.accepted:
        fields: dict = {
            "status": OutboxMessage.Status.SENT,
            "provider_id": (result.provider_id or "")[:64],
            "sent_at": now,
            "body": "",
            "last_error": "",
        }
    elif result.retryable and message.attempts < MAX_ATTEMPTS:
        fields = {
            "status": OutboxMessage.Status.PENDING,
            "next_attempt_at": now + backoff(message.attempts),
            "last_error": (result.error or "")[:100],
        }
    else:
        fields = {
            "status": OutboxMessage.Status.FAILED,
            "body": "",
            "last_error": (result.error or "")[:100],
        }
    OutboxMessage.objects.filter(pk=message.pk, status=OutboxMessage.Status.SENDING).update(
        claimed_at=None, **fields
    )
    return str(fields["status"])


def due_ids() -> list[int]:
    """Ids of messages that are waiting and due, oldest first."""
    return list(
        OutboxMessage.objects.filter(
            status=OutboxMessage.Status.PENDING, next_attempt_at__lte=timezone.now()
        )
        .order_by("next_attempt_at")
        .values_list("pk", flat=True)[:BATCH_SIZE]
    )


def release_stuck() -> int:
    """Put back messages a worker claimed and never finished. Returns how many."""
    now = timezone.now()
    return OutboxMessage.objects.filter(
        status=OutboxMessage.Status.SENDING, claimed_at__lt=now - STUCK_AFTER
    ).update(status=OutboxMessage.Status.PENDING, claimed_at=None, next_attempt_at=now)
