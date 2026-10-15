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
