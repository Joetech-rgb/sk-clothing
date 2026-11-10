from django.contrib import admin, messages
from django.db.models import QuerySet
from django.http import HttpRequest

from apps.delivery import code_services as delivery_codes

from .models import Order, OrderEvent, OrderLine
from .services import dispatch_order, mark_packed
from .states import InvalidTransition


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


def _actor(request: HttpRequest) -> str:
    return f"user:{request.user.pk}"


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    """Read-only. Status changes happen through services.transition(), never by editing a field.

    The three actions call the order services, so they follow the same transition table as
    everything else. Each needs its own permission. No action ever shows a delivery code.
    """

    list_display = ("reference", "payment", "fulfilment", "refund", "pickup", "created_at")
    list_filter = ("payment", "fulfilment", "refund", "pickup")
    search_fields = ("reference",)
    inlines = [OrderLineInline, OrderEventInline]
    actions = ["mark_packed_action", "dispatch_action", "reissue_code_action"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_pack_permission(self, request: HttpRequest) -> bool:
        return request.user.has_perm("orders.pack_order")

    def has_dispatch_permission(self, request: HttpRequest) -> bool:
        return request.user.has_perm("orders.dispatch_order")

    def has_reissue_permission(self, request: HttpRequest) -> bool:
        return request.user.has_perm("orders.reissue_delivery_code")

    def _report(self, request: HttpRequest, what: str, done: int, skipped: int) -> None:
        if done:
            self.message_user(request, f"{done} order(s) {what}.", messages.SUCCESS)
        if skipped:
            self.message_user(
                request,
                f"{skipped} order(s) skipped: not in a state where this applies.",
                messages.WARNING,
            )

    @admin.action(description="Mark selected orders as packed", permissions=["pack"])
    def mark_packed_action(self, request: HttpRequest, queryset: QuerySet[Order]) -> None:
        done = skipped = 0
        for order in queryset:
            try:
                mark_packed(order.pk, actor=_actor(request))
                done += 1
            except InvalidTransition:
                skipped += 1
        self._report(request, "marked as packed", done, skipped)

    @admin.action(
        description="Send selected orders out for delivery (issues the delivery code)",
        permissions=["dispatch"],
    )
    def dispatch_action(self, request: HttpRequest, queryset: QuerySet[Order]) -> None:
        done = skipped = 0
        for order in queryset:
            try:
                dispatch_order(order.pk, actor=_actor(request))
                done += 1
            except InvalidTransition:
                skipped += 1
        self._report(request, "sent out for delivery", done, skipped)

    @admin.action(
        description="Issue a new delivery code (for a locked or lost code)",
        permissions=["reissue"],
    )
    def reissue_code_action(self, request: HttpRequest, queryset: QuerySet[Order]) -> None:
        done = skipped = 0
        for order in queryset:
            try:
                delivery_codes.reissue_delivery_code(order.pk, actor=_actor(request))
                done += 1
            except (delivery_codes.CodeNotIssued, delivery_codes.CodeAlreadyUsed):
                skipped += 1
        what = "given a new delivery code (the customer sees it on the order page)"
        self._report(request, what, done, skipped)
