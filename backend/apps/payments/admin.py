"""Staff screens for refunds and payments. Staff never edit a refund's fields: they can record that
a refund that needs a person was made outside the system, and that goes through the refund service
so it is attributed, logged and applied to the order."""

from django import forms
from django.contrib import admin

from . import refunds
from .models import PaymentAttempt, Refund, RefundEvent


class RefundEventInline(admin.TabularInline):
    model = RefundEvent
    extra = 0
    can_delete = False
    readonly_fields = ("kind", "actor", "detail", "created_at")

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class RefundResolutionForm(forms.ModelForm):
    outcome = forms.ChoiceField(
        required=False,
        label="Record an outcome",
        choices=[("", "No change"), ("resolved_outside", "The refund was made outside the system")],
    )
    note = forms.CharField(
        required=False,
        max_length=300,
        label="How and where it was refunded",
        help_text="For example: refunded in the Paystack dashboard, or by mobile money.",
    )

    class Meta:
        model = Refund
        fields: list[str] = []

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("outcome"):
            if self.instance.status != Refund.Status.MANUAL_RESOLUTION:
                raise forms.ValidationError("Only a refund that needs a person can be resolved.")
            if not (cleaned.get("note") or "").strip():
                raise forms.ValidationError("Say how and where the refund was made.")
        return cleaned


READ_ONLY = (
    "payment",
    "order_id",
    "reason",
    "amount_pesewas",
    "currency",
    "status",
    "attempts",
    "last_error",
    "next_attempt_at",
    "submitted_at",
    "checked_at",
    "processed_at",
    "resolved_by",
    "resolution_note",
    "created_at",
)


@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):
    form = RefundResolutionForm
    list_display = (
        "id",
        "order_id",
        "reason",
        "status",
        "amount_pesewas",
        "attempts",
        "created_at",
    )
    list_filter = ("status", "reason")
    search_fields = ("payment__reference",)
    readonly_fields = READ_ONLY
    fields = (*READ_ONLY, "outcome", "note")
    inlines = [RefundEventInline]

    def save_model(self, request, obj, form, change):
        if form.cleaned_data.get("outcome") == "resolved_outside":
            refunds.resolve_outside_system(
                obj.pk, actor=f"user:{request.user.pk}", note=form.cleaned_data["note"]
            )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PaymentAttempt)
class PaymentAttemptAdmin(admin.ModelAdmin):
    """Read only. Shows which payments were applied, and which need a person."""

    list_display = ("reference", "order_id", "amount_pesewas", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("reference",)

    def get_readonly_fields(self, request, obj=None):
        return [field.name for field in self.model._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
