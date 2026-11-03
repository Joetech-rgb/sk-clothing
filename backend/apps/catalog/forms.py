from decimal import Decimal
from typing import Any

from django import forms
from django.core.exceptions import ValidationError

from apps.pricing.money import Money

from .models import PriceTier


class PriceTierForm(forms.ModelForm):
    """Staff type cedis (12.50). The database stores whole pesewas (1250)."""

    price_ghs = forms.DecimalField(
        label="Price (GHS)", min_value=Decimal("0"), max_digits=12, decimal_places=2
    )

    class Meta:
        model = PriceTier
        fields = ["tier"]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["price_ghs"].initial = Money(self.instance.price_pesewas).to_ghs()

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean() or {}
        price = cleaned.get("price_ghs")
        if price is not None:
            self.instance.price_pesewas = Money.from_ghs(price).pesewas
        return cleaned


class PriceTierFormSet(forms.BaseInlineFormSet):
    def clean(self) -> None:
        super().clean()
        if any(self.errors):
            return
        tiers = [
            form.cleaned_data.get("tier")
            for form in self.forms
            if form.cleaned_data and not form.cleaned_data.get("DELETE")
        ]
        if PriceTier.Tier.RETAIL not in tiers:
            raise ValidationError("Every variant needs a retail price.")
