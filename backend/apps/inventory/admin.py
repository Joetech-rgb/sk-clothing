from django.contrib import admin
from django.http import HttpRequest

from .models import Batch, Reservation, StockLevel, StockMovement


class ReadOnlyAdmin(admin.ModelAdmin):
    """Stock is changed only through services.py, never by editing a row by hand."""

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: object = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: object = None) -> bool:
        return False


@admin.register(StockLevel)
class StockLevelAdmin(ReadOnlyAdmin):
    list_display = ("variant_id", "on_hand", "reserved", "updated_at")
    search_fields = ("variant_id",)


@admin.register(Batch)
class BatchAdmin(ReadOnlyAdmin):
    list_display = ("id", "variant_id", "quantity_received", "quantity_remaining", "received_at")
    search_fields = ("variant_id",)


@admin.register(Reservation)
class ReservationAdmin(ReadOnlyAdmin):
    list_display = ("id", "variant_id", "quantity", "status", "expires_at")
    list_filter = ("status",)


@admin.register(StockMovement)
class StockMovementAdmin(ReadOnlyAdmin):
    list_display = ("id", "variant_id", "kind", "quantity", "batch", "created_at")
    list_filter = ("kind",)
