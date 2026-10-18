from django.db import models


class Category(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="children"
    )
    position = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["position", "name"]
        verbose_name_plural = "categories"

    def __str__(self) -> str:
        return self.name


class Product(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    description = models.TextField(blank=True)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Variant(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variants")
    sku = models.CharField(max_length=64, unique=True)
    size = models.CharField(max_length=32, blank=True)
    colour = models.CharField(max_length=32, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sku"]
        constraints = [
            models.UniqueConstraint(
                fields=["product", "size", "colour"], name="variant_unique_options"
            )
        ]

    def __str__(self) -> str:
        return self.sku


class PriceTier(models.Model):
    """One price per variant per tier, in whole pesewas. A tier that is not filled in has no row."""

    class Tier(models.TextChoices):
        RETAIL = "retail", "Retail"
        WHOLESALE = "wholesale", "Wholesale"
        DEALER = "dealer", "Dealer"
        BULK = "bulk", "Bulk"

    variant = models.ForeignKey(Variant, on_delete=models.CASCADE, related_name="tiers")
    tier = models.CharField(max_length=16, choices=Tier.choices)
    # PositiveBigIntegerField adds a database check that the value is zero or more.
    price_pesewas = models.PositiveBigIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["variant", "tier"], name="pricetier_one_per_variant_tier"
            )
        ]

    def __str__(self) -> str:
        return f"{self.variant_id}:{self.tier}"


class ProductImage(models.Model):
    """Photo metadata only. Upload to R2 and WebP resizing arrive in a later pull request."""

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    storage_key = models.CharField(max_length=255)
    alt_text = models.CharField(max_length=200, blank=True)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["position", "id"]

    def __str__(self) -> str:
        return self.storage_key
