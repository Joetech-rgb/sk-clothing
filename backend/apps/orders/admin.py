from django.contrib import admin

from .models import Order, OrderEvent, OrderLine


class _ReadOnlyInline(admin.TabularInline):
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class OrderLineInline(_ReadOnlyInline):
    model = OrderLine


class OrderEventInline(_ReadOnlyInline):
    model = OrderEvent


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    """Read-only. Status changes happen through services.transition(), never by editing a field."""

    list_display = ("reference", "payment", "fulfilment", "refund", "pickup", "created_at")
    list_filter = ("payment", "fulfilment", "refund", "pickup")
    search_fields = ("reference",)
    inlines = [OrderLineInline, OrderEventInline]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
