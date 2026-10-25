from decimal import Decimal
from typing import Any

from django import forms

from apps.pricing.money import Money

from .fees import normalise_station_name
from .models import DeliverySettings, Station


def _ghs_field(label: str) -> forms.DecimalField:
    return forms.DecimalField(label=label, min_value=Decimal("0"), max_digits=12, decimal_places=2)


class StationForm(forms.ModelForm):
    """Staff type the fee in cedis (20.50). The database stores whole pesewas (2050)."""

    fee_ghs = _ghs_field("Fee (GHS)")

    class Meta:
        model = Station
        fields = ["name", "is_active"]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["fee_ghs"].initial = Money(self.instance.fee_pesewas).to_ghs()

    def clean_name(self) -> str:
        name = " ".join(self.cleaned_data["name"].split())
        taken = Station.objects.filter(name_key=normalise_station_name(name))
        if taken.exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("A station with this name already exists.")
        return name

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean() or {}
        fee = cleaned.get("fee_ghs")
        if fee is not None:
            self.instance.fee_pesewas = Money.from_ghs(fee).pesewas
        return cleaned


class DeliverySettingsForm(forms.ModelForm):
    minimum_fee_ghs = _ghs_field("Minimum fee (GHS)")
    base_fee_ghs = _ghs_field("Base fee (GHS)")
    rate_per_km_ghs = _ghs_field("Rate per km (GHS)")

    class Meta:
        model = DeliverySettings
        fields = ["shop_latitude", "shop_longitude", "max_distance_km", "road_factor"]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            for field, pesewas in (
                ("minimum_fee_ghs", self.instance.minimum_fee_pesewas),
                ("base_fee_ghs", self.instance.base_fee_pesewas),
                ("rate_per_km_ghs", self.instance.rate_per_km_pesewas),
            ):
                self.fields[field].initial = Money(pesewas).to_ghs()

    def clean_shop_latitude(self) -> Decimal:
        value = self.cleaned_data["shop_latitude"]
        if not Decimal(-90) <= value <= Decimal(90):
            raise forms.ValidationError("Latitude must be between -90 and 90.")
        return value

    def clean_shop_longitude(self) -> Decimal:
        value = self.cleaned_data["shop_longitude"]
        if not Decimal(-180) <= value <= Decimal(180):
            raise forms.ValidationError("Longitude must be between -180 and 180.")
        return value

    def clean_max_distance_km(self) -> Decimal:
        value = self.cleaned_data["max_distance_km"]
        if value <= 0:
            raise forms.ValidationError("The maximum distance must be above zero.")
        return value

    def clean_road_factor(self) -> Decimal:
        value = self.cleaned_data["road_factor"]
        if value <= 0:
            raise forms.ValidationError("The road factor must be above zero.")
        return value

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean() or {}
        for field, attribute in (
            ("minimum_fee_ghs", "minimum_fee_pesewas"),
            ("base_fee_ghs", "base_fee_pesewas"),
            ("rate_per_km_ghs", "rate_per_km_pesewas"),
        ):
            value = cleaned.get(field)
            if value is not None:
                setattr(self.instance, attribute, Money.from_ghs(value).pesewas)
        return cleaned
