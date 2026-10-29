"""Order records. State changes go through services.transition(), never by editing fields.

Other apps are referenced by plain integer ids (variant_id, vendor_id), not foreign keys, so apps
never import each other's models and order history survives catalog edits. The only foreign key is
the customer, who may be absent (guest checkout).
"""

import secrets

from django.conf import settings
from django.db import models
from django.db.models import F, Q

from .states import Fulfilment, OrderState, Payment, Refund

_REFERENCE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I


def new_reference() -> str:
    return "SK" + "".join(secrets.choice(_REFERENCE_ALPHABET) for _ in range(10))


def _choices(enum_class: type) -> list[tuple[str, str]]:
    return [(member.value, member.value) for member in enum_class]


class ImmutableError(RuntimeError):
    """Raised when code tries to change or delete a row that must never change."""


class AppendOnlyQuerySet(models.QuerySet):
    def update(self, **kwargs):  # type: ignore[override]
        raise ImmutableError(f"{self.model.__name__} rows cannot be updated")

    def delete(self):  # type: ignore[override]
        raise ImmutableError(f"{self.model.__name__} rows cannot be deleted")


class AppendOnlyModel(models.Model):
    objects = AppendOnlyQuerySet.as_manager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ImmutableError(f"{type(self).__name__} rows cannot be changed once written")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ImmutableError(f"{type(self).__name__} rows cannot be deleted")


class Order(models.Model):
    reference = models.CharField(max_length=12, unique=True, default=new_reference, editable=False)
    idempotency_key = models.CharField(max_length=64, unique=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    contact_phone = models.CharField(max_length=16, blank=True)  # E.164; never logged

    # Three separate status fields. Change them only through services.transition().
    payment = models.CharField(max_length=24, choices=_choices(Payment))
    fulfilment = models.CharField(max_length=24, choices=_choices(Fulfilment))
    refund = models.CharField(max_length=24, choices=_choices(Refund), default=Refund.NONE.value)
    pickup = models.BooleanField()  # fixed at creation, never changes

    # A hash of what the customer asked for, to tell a retry from a different request.
    request_hash = models.CharField(max_length=64, blank=True)
    contact_name = models.CharField(max_length=120, blank=True)
    delivery_details = models.JSONField(default=dict, blank=True)  # station, address, map pin

    delivery_method = models.CharField(max_length=24)
    delivery_fee_pesewas = models.BigIntegerField(null=True, blank=True)  # null: awaiting quote
    subtotal_pesewas = models.BigIntegerField()

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(subtotal_pesewas__gte=0), name="order_subtotal_not_negative"
            ),
            models.CheckConstraint(
                condition=Q(delivery_fee_pesewas__isnull=True) | Q(delivery_fee_pesewas__gte=0),
                name="order_delivery_fee_not_negative",
            ),
        ]

    def __str__(self) -> str:
        return self.reference

    @property
    def state(self) -> OrderState:
        return OrderState(
            Payment(self.payment), Fulfilment(self.fulfilment), Refund(self.refund), self.pickup
        )

    @property
    def total_pesewas(self) -> int | None:
        """Subtotal plus delivery fee; None until the fee is known."""
        if self.delivery_fee_pesewas is None:
            return None
        return self.subtotal_pesewas + self.delivery_fee_pesewas

    def delete(self, *args, **kwargs):
        raise ImmutableError("orders are never deleted; cancel them instead")


class SubOrder(models.Model):
    """One per order for now. Vendor orders (Phase 5) will split into several."""

    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name="sub_order")
    vendor_id = models.BigIntegerField(null=True, blank=True)  # null: sold by S.K itself
    created_at = models.DateTimeField(auto_now_add=True)


class OrderLine(AppendOnlyModel):
    """Everything on a line is frozen when the order is created."""

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="lines")
    variant_id = models.BigIntegerField(db_index=True)
    name = models.CharField(max_length=200)  # product and variant name as the customer saw it
    quantity = models.PositiveIntegerField()
    tier = models.CharField(max_length=16)  # tier whose price applied before any discount
    unit_price_pesewas = models.BigIntegerField()
    line_total_pesewas = models.BigIntegerField()
    list_price_pesewas = models.BigIntegerField()
    tier_price_pesewas = models.BigIntegerField()
    source = models.CharField(max_length=16)  # "tier" or "discount"
    discounts = models.JSONField(default=list, blank=True)  # applied-discount details, as priced

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gte=1), name="orderline_quantity_min_1"),
            models.CheckConstraint(
                condition=Q(unit_price_pesewas__gte=0), name="orderline_price_not_negative"
            ),
            models.CheckConstraint(
                condition=Q(line_total_pesewas=F("unit_price_pesewas") * F("quantity")),
                name="orderline_total_is_price_times_quantity",
            ),
        ]


class OrderEvent(AppendOnlyModel):
    """The history of an order. One row per real state change, plus one for creation."""

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="events")
    event = models.CharField(max_length=32)  # an states.Event value, or "created"
    before = models.JSONField(null=True, blank=True)
    after = models.JSONField()
    actor = models.CharField(max_length=64)  # e.g. "system:paystack_webhook", "user:12"
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]


class OrderReservation(AppendOnlyModel):
    """The stock holds taken for an order, so payment can later confirm them and expiry can
    release them. The hold itself lives in inventory; this row only remembers its id."""

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="reservations")
    reservation_id = models.BigIntegerField(unique=True)
    variant_id = models.BigIntegerField()
    quantity = models.PositiveIntegerField()
    expires_at = models.DateTimeField()

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(quantity__gte=1), name="orderreservation_quantity_min_1"
            ),
        ]
