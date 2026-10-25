"""Delivery data the admin manages: the station table and the shop's delivery settings.

Fees are whole pesewas. Staff type cedis in the admin and the forms convert.
"""

from decimal import Decimal
from typing import Any

from django.db import models

from .fees import normalise_station_name


class Station(models.Model):
    """A station the shop delivers to, with its fee. Names match ignoring case and spacing."""

    name = models.CharField(max_length=100)
    name_key = models.CharField(max_length=100, unique=True, editable=False)
    fee_pesewas = models.PositiveBigIntegerField()
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.name = " ".join(self.name.split())
        self.name_key = normalise_station_name(self.name)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.name


class DeliverySettings(models.Model):
    """The shop's doorstep delivery settings. There is exactly one row, or none.

    Until staff fill these in, doorstep orders go to "awaiting quote": no number is guessed.
    """

    shop_latitude = models.DecimalField(max_digits=9, decimal_places=6)
    shop_longitude = models.DecimalField(max_digits=9, decimal_places=6)
    minimum_fee_pesewas = models.PositiveBigIntegerField()
    base_fee_pesewas = models.PositiveBigIntegerField()
    rate_per_km_pesewas = models.PositiveBigIntegerField()
    max_distance_km = models.DecimalField(max_digits=6, decimal_places=2)
    road_factor = models.DecimalField(max_digits=4, decimal_places=2, default=Decimal("1.30"))
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "delivery settings"
        constraints = [
            models.CheckConstraint(condition=models.Q(id=1), name="deliverysettings_single_row"),
            models.CheckConstraint(
                condition=models.Q(max_distance_km__gt=0), name="deliverysettings_distance_positive"
            ),
            models.CheckConstraint(
                condition=models.Q(road_factor__gt=0), name="deliverysettings_road_factor_positive"
            ),
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.pk = 1
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return "Delivery settings"
