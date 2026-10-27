from django.contrib import admin

from .models import FeatureFlag, FlagChange
from .services import set_flag


@admin.register(FeatureFlag)
class FeatureFlagAdmin(admin.ModelAdmin):
    """Every save goes through set_flag(), so it is attributed to the staff member."""

    list_display = ("key", "enabled", "description", "updated_at")
    list_editable = ("enabled",)
    search_fields = ("key", "description")

    def get_readonly_fields(self, request, obj=None):
        return ("key",) if obj else ()

    def save_model(self, request, obj, form, change):
        flag = set_flag(
            obj.key, obj.enabled, actor=f"user:{request.user.pk}", description=obj.description
        )
        obj.pk = flag.pk

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(FlagChange)
class FlagChangeAdmin(admin.ModelAdmin):
    list_display = ("created_at", "flag_key", "actor", "before", "after")
    list_filter = ("flag_key",)
    search_fields = ("flag_key", "actor")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
