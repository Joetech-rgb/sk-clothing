"""The outbox: messages waiting to be sent, written in the same transaction as the event that
caused them, so a message is never lost and (with its idempotency key) never sent twice.

The recipient is stored in E.164 and the body only while the message is waiting: both are cleared
or never logged. The body is blanked as soon as the message reaches a final state, because some
bodies hold a delivery code.
"""

from django.db import models
from django.utils import timezone


class OutboxMessage(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "pending"  # waiting for its turn, or waiting to be retried
        SENDING = "sending", "sending"  # claimed by a worker
        SENT = "sent", "sent"
        FAILED = "failed", "failed"  # gave up: not retryable, or out of attempts

    channel = models.CharField(max_length=8, default="sms")
    recipient = models.CharField(max_length=32)  # E.164. Never logged.
    template = models.CharField(max_length=64)  # which message this is, e.g. "delivery_code"
    body = models.TextField(blank=True)  # cleared once the message is sent or has failed
    idempotency_key = models.CharField(max_length=128, unique=True)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.PENDING)
    attempts = models.PositiveSmallIntegerField(default=0)
    next_attempt_at = models.DateTimeField(default=timezone.now)
    claimed_at = models.DateTimeField(null=True, blank=True)
    provider_id = models.CharField(max_length=64, blank=True)
    last_error = models.CharField(max_length=100, blank=True)  # a short code, never a body
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["id"]
        indexes = [models.Index(fields=["status", "next_attempt_at"], name="outbox_due_idx")]

    def __str__(self) -> str:  # no recipient, no body
        return f"{self.template} #{self.pk} ({self.status})"
