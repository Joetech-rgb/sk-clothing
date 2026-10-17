from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest

from apps.pricing.money import Money

from .forms import PriceTierForm, PriceTierFormSet
from .models import Category, PriceTier, Product, ProductImage, Variant


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "parent", "position", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name",)}


class VariantInline(admin.TabularInline):
    """Add sizes and colours here, then open each variant (change link) to set its prices."""

    model = Variant
    extra = 1
    fields = ("sku", "size", "colour", "is_active")
    show_change_link = True


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 0
    fields = ("storage_key", "alt_text", "position")


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "is_active")
    list_filter = ("is_active", "category")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [VariantInline, ProductImageInline]


class PriceTierInline(admin.TabularInline):
    model = PriceTier
    form = PriceTierForm
    formset = PriceTierFormSet
    extra = 1
    max_num = len(PriceTier.Tier.values)
    fields = ("tier", "price_ghs")


@admin.register(Variant)
class VariantAdmin(admin.ModelAdmin):
    list_display = ("sku", "product", "size", "colour", "retail_price", "is_active")
    list_filter = ("is_active",)
    list_select_related = ("product",)
    search_fields = ("sku", "product__name")
    inlines = [PriceTierInline]

    def get_queryset(self, request: HttpRequest) -> QuerySet[Variant]:
        return super().get_queryset(request).prefetch_related("tiers")

    @admin.display(description="Retail price")
    def retail_price(self, obj: Variant) -> str:
        for tier in obj.tiers.all():
            if tier.tier == PriceTier.Tier.RETAIL:
                return str(Money(tier.price_pesewas))
        return "MISSING"
