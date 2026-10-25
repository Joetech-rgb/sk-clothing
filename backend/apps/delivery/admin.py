from django.contrib import admin
from django.http import HttpRequest

from apps.pricing.money import Money

from .forms import DeliverySettingsForm, StationForm
from .models import DeliverySettings, Station


@admin.register(Station)
class StationAdmin(admin.ModelAdmin):
    form = StationForm
    list_display = ("name", "fee", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)
    fields = ("name", "fee_ghs", "is_active")

    @admin.display(description="Fee")
    def fee(self, obj: Station) -> str:
        return str(Money(obj.fee_pesewas))


@admin.register(DeliverySettings)
class DeliverySettingsAdmin(admin.ModelAdmin):
    """One settings record for the whole shop. Until it exists, doorstep orders wait for a quote."""

    form = DeliverySettingsForm
    fieldsets = (
        ("Shop location", {"fields": ("shop_latitude", "shop_longitude")}),
        ("Doorstep fee", {"fields": ("minimum_fee_ghs", "base_fee_ghs", "rate_per_km_ghs")}),
        ("Limits", {"fields": ("max_distance_km", "road_factor")}),
    )

    def has_add_permission(self, request: HttpRequest) -> bool:
        return not DeliverySettings.objects.exists()

    def has_delete_permission(self, request: HttpRequest, obj: object = None) -> bool:
        return False
