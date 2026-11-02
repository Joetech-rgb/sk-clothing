from django.db import models


class PaystackWebhookEvent(models.Model):
    """One row per distinct Paystack event. The unique key makes replays harmless.

    Deliberately stores only these fields, not the full payload, so no customer or
    card details are kept.
    """

    dedupe_key = models.CharField(max_length=200, unique=True)
    event_type = models.CharField(max_length=64)
    reference = models.CharField(max_length=100)
    amount = models.BigIntegerField(null=True, blank=True)  # integer pesewas
    currency = models.CharField(max_length=3, blank=True)
    received_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.dedupe_key


class PaymentAttempt(models.Model):
    """One try at paying for an order. An order may have several (a card is declined, the
    customer tries again). Each has its own Paystack reference.

    The order is held as a plain id, not a foreign key: apps never import each other's models.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Waiting for the customer"
        SUCCESS = "success", "Paid and applied to the order"
        FAILED = "failed", "Failed or could not be started"
        MISMATCH = "mismatch", "Paid, but the amount or currency was wrong"
        DUPLICATE = "duplicate", "Paid, but the order was already paid"

    order_id = models.BigIntegerField()
    reference = models.CharField(max_length=100, unique=True)
    amount_pesewas = models.PositiveBigIntegerField()  # always the order total, never from a client
    currency = models.CharField(max_length=3, default="GHS")
    payer_email = models.CharField(max_length=254)  # Paystack needs one; also for refund news
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["order_id", "created_at"], name="attempt_order_created")]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount_pesewas__gt=0), name="attempt_amount_positive"
            )
        ]

    def __str__(self) -> str:
        return self.reference


class ImmutableError(RuntimeError):
    pass


class _ImmutableQuerySet(models.QuerySet):
    def update(self, **kwargs):  # type: ignore[override]
        raise ImmutableError("history rows cannot be updated")

    def delete(self):  # type: ignore[override]
        raise ImmutableError("history rows cannot be deleted")


class Refund(models.Model):
    """Money going back to a customer for one payment. At most one per payment: the unique link
    means a double trigger can never refund twice (ADR 0008).

    `status` here is the refund's own progress. For a refund of an order, the order's refund
    status (orders app) follows it through the same steps.
    """

    class Status(models.TextChoices):
        REQUESTED = "requested", "Waiting to be sent to Paystack"
        SUBMITTED = "submitted", "Sent to Paystack"
        PROCESSING = "processing", "Being processed by Paystack"
        PROCESSED = "processed", "Done"
        MANUAL_RESOLUTION = "manual_resolution", "Needs a person"

    class Reason(models.TextChoices):
        ORDER = "order_refund", "Order could not be fulfilled or was cancelled"
        DUPLICATE = "duplicate_payment", "Paid twice"

    payment = models.OneToOneField(PaymentAttempt, on_delete=models.PROTECT, related_name="refund")
    order_id = models.BigIntegerField(db_index=True)
    reason = models.CharField(max_length=24, choices=Reason.choices)
    amount_pesewas = models.PositiveBigIntegerField()  # always the full payment
    currency = models.CharField(max_length=3, default="GHS")
    idempotency_key = models.CharField(max_length=120, unique=True)  # refund:{payment reference}
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.REQUESTED)
    paystack_refund_id = models.CharField(max_length=64, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.CharField(max_length=64, blank=True)  # a short code, never Paystack's text
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    checked_at = models.DateTimeField(null=True, blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.CharField(max_length=64, blank=True)
    resolution_note = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["status", "next_attempt_at"], name="refund_status_due")]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount_pesewas__gt=0), name="refund_amount_positive"
            )
        ]

    def __str__(self) -> str:
        return f"refund {self.pk} ({self.status})"


class RefundEvent(models.Model):
    """Append-only history of a refund: what happened, who did it, and when."""

    refund = models.ForeignKey(Refund, on_delete=models.CASCADE, related_name="events")
    kind = models.CharField(max_length=32)
    actor = models.CharField(max_length=64)  # "system", or "user:12" for staff
    detail = models.CharField(max_length=300, blank=True)  # never personal data
    created_at = models.DateTimeField(auto_now_add=True)

    objects = _ImmutableQuerySet.as_manager()

    class Meta:
        ordering = ["id"]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ImmutableError("history rows cannot be changed")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ImmutableError("history rows cannot be deleted")
