"""Stock tables.

`variant_id` is a plain integer, not a foreign key: apps never import each other's models
(CLAUDE.md section 4), so inventory knows a variant only by its id. The catalog service is
asked whether a variant exists, before stock is received for it.

Nothing here is edited directly. Every change goes through services.py, which writes the
append-only StockMovement rows and the cached numbers in one transaction.
"""

from django.db import models
from django.utils import timezone


class Batch(models.Model):
    """One receipt of stock for a variant. FIFO consumes the oldest batch first."""

    variant_id = models.BigIntegerField()
    quantity_received = models.PositiveIntegerField()
    quantity_remaining = models.PositiveIntegerField()  # cache, kept in step with movements
    # Landed cost per item. Filled by costing in Phase 3, so it may be empty until then.
    unit_cost_pesewas = models.PositiveBigIntegerField(null=True, blank=True)
    received_at = models.DateTimeField(default=timezone.now)
    idempotency_key = models.CharField(max_length=100, unique=True)

    class Meta:
        indexes = [models.Index(fields=["variant_id", "received_at", "id"], name="batch_fifo")]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity_remaining__lte=models.F("quantity_received")),
                name="batch_remaining_within_received",
            ),
            models.CheckConstraint(
                condition=models.Q(quantity_received__gt=0), name="batch_received_positive"
            ),
        ]

    def __str__(self) -> str:
        return f"batch {self.pk} variant {self.variant_id}"


class StockLevel(models.Model):
    """A cache of the totals for one variant. The movements are the source of truth."""

    variant_id = models.BigIntegerField(unique=True)
    on_hand = models.PositiveIntegerField(default=0)  # the database refuses below zero
    reserved = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(reserved__lte=models.F("on_hand")),
                name="stocklevel_reserved_within_on_hand",
            )
        ]

    def __str__(self) -> str:
        return f"variant {self.variant_id}: {self.on_hand} on hand, {self.reserved} reserved"


class ReservationStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    CONFIRMED = "confirmed", "Confirmed"
    RELEASED = "released", "Released"
    EXPIRED = "expired", "Expired"


class Reservation(models.Model):
    """A hold on stock while a customer pays. Expires after 15 minutes."""

    variant_id = models.BigIntegerField()
    quantity = models.PositiveIntegerField()
    status = models.CharField(
        max_length=16, choices=ReservationStatus.choices, default=ReservationStatus.ACTIVE
    )
    idempotency_key = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        indexes = [
            models.Index(fields=["status", "expires_at"], name="reservation_status_expiry"),
            models.Index(fields=["variant_id", "status"], name="reservation_variant_status"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0), name="reservation_quantity_positive"
            )
        ]

    def __str__(self) -> str:
        return f"reservation {self.pk} ({self.status})"


class MovementKind(models.TextChoices):
    RECEIPT = "receipt", "Receipt"
    SALE = "sale", "Sale"


class StockMovement(models.Model):
    """Append-only. A database trigger refuses any UPDATE or DELETE on this table."""

    variant_id = models.BigIntegerField()
    batch = models.ForeignKey(Batch, on_delete=models.PROTECT, related_name="movements")
    kind = models.CharField(max_length=16, choices=MovementKind.choices)
    quantity = models.IntegerField()  # positive in, negative out
    idempotency_key = models.CharField(max_length=100)
    reservation = models.ForeignKey(
        Reservation, null=True, blank=True, on_delete=models.PROTECT, related_name="movements"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["variant_id"], name="movement_variant")]
        constraints = [
            models.CheckConstraint(condition=~models.Q(quantity=0), name="movement_not_zero"),
            models.UniqueConstraint(
                fields=["idempotency_key", "batch"], name="movement_once_per_key_batch"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.kind} {self.quantity} (batch {self.batch_id})"
