"""Request and response shapes. They describe the API (OpenAPI, and the typed client built from
it) and render the dictionaries the browse and price services return."""

from rest_framework import serializers

from .search import MAX_PAGE_SIZE, SORTS

MAX_CART_LINES = 50
MAX_LINE_QUANTITY = 10_000


class MoneySerializer(serializers.Serializer):
    pesewas = serializers.IntegerField()
    display = serializers.CharField()


class TierSerializer(serializers.Serializer):
    tier = serializers.CharField()
    min_quantity = serializers.IntegerField()
    price = MoneySerializer()


class QuantityRuleSerializer(serializers.Serializer):
    tier = serializers.CharField()
    min_quantity = serializers.IntegerField()


class CategorySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    slug = serializers.CharField()
    parent_id = serializers.IntegerField(allow_null=True)


class CategoryRefSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    slug = serializers.CharField()


class ImageSerializer(serializers.Serializer):
    url = serializers.CharField()
    alt_text = serializers.CharField(allow_blank=True)


class ProductListItemSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    slug = serializers.CharField()
    category = CategoryRefSerializer()
    image = ImageSerializer(allow_null=True)
    price_from = MoneySerializer(allow_null=True)
    in_stock = serializers.BooleanField()
    has_wholesale = serializers.BooleanField()


class ProductPageSerializer(serializers.Serializer):
    results = ProductListItemSerializer(many=True)
    next_cursor = serializers.CharField(allow_null=True)


class VariantSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    sku = serializers.CharField()
    size = serializers.CharField(allow_blank=True)
    colour = serializers.CharField(allow_blank=True)
    available = serializers.IntegerField()
    in_stock = serializers.BooleanField()
    tiers = TierSerializer(many=True)


class ProductDetailSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    slug = serializers.CharField()
    description = serializers.CharField(allow_blank=True)
    category = CategoryRefSerializer()
    images = ImageSerializer(many=True)
    price_from = MoneySerializer(allow_null=True)
    quantity_rules = QuantityRuleSerializer(many=True)
    variants = VariantSerializer(many=True)


class ProductListQuerySerializer(serializers.Serializer):
    q = serializers.CharField(required=False, allow_blank=True, max_length=200, default="")
    category = serializers.SlugField(required=False)
    sort = serializers.ChoiceField(choices=sorted(SORTS), default="relevance")
    limit = serializers.IntegerField(min_value=1, max_value=MAX_PAGE_SIZE, default=24)
    cursor = serializers.CharField(required=False, allow_blank=True, max_length=64)


class PriceItemSerializer(serializers.Serializer):
    variant_id = serializers.IntegerField(min_value=1)
    quantity = serializers.IntegerField(min_value=1, max_value=MAX_LINE_QUANTITY)

    def to_internal_value(self, data):  # type: ignore[no-untyped-def]
        # The client sends what it wants to buy, never what it should pay. Anything else, such
        # as a price, is refused loudly rather than quietly ignored.
        if isinstance(data, dict):
            unknown = sorted(set(data) - set(self.fields))
            if unknown:
                raise serializers.ValidationError(
                    {key: "This field is not accepted." for key in unknown}
                )
        return super().to_internal_value(data)


class PriceRequestSerializer(serializers.Serializer):
    items = PriceItemSerializer(many=True, allow_empty=False, max_length=MAX_CART_LINES)

    def validate_items(self, items):  # type: ignore[no-untyped-def]
        ids = [item["variant_id"] for item in items]
        if len(set(ids)) != len(ids):
            raise serializers.ValidationError("Each item may appear once; add the quantities.")
        return items


class AppliedDiscountSerializer(serializers.Serializer):
    discount_id = serializers.IntegerField()
    kind = serializers.CharField()
    value = serializers.IntegerField()
    unit_price_after = MoneySerializer()


class PricedLineSerializer(serializers.Serializer):
    variant_id = serializers.IntegerField()
    quantity = serializers.IntegerField()
    tier = serializers.CharField()
    source = serializers.CharField()
    unit_price = MoneySerializer()
    line_total = MoneySerializer()
    list_price = MoneySerializer()
    tier_price = MoneySerializer()
    discounts = AppliedDiscountSerializer(many=True)


class PriceResponseSerializer(serializers.Serializer):
    lines = PricedLineSerializer(many=True)
    subtotal = MoneySerializer()
