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
