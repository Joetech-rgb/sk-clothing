import pytest

from apps.catalog.models import Category, PriceTier, Product, Variant
from apps.catalog.services import CartItem, CatalogError, price_cart
from apps.pricing.money import Money
from apps.pricing.services import PricingError


@pytest.fixture
def product(db):
    category = Category.objects.create(name="Shirts", slug="shirts")
    return Product.objects.create(name="Kente shirt", slug="kente-shirt", category=category)


def make_variant(product, sku, tiers, **options):
    variant = Variant.objects.create(product=product, sku=sku, **options)
    for tier, pesewas in tiers.items():
        PriceTier.objects.create(variant=variant, tier=tier, price_pesewas=pesewas)
    return variant


def test_single_item_uses_retail_below_ten(product):
    variant = make_variant(product, "KS-1", {"retail": 1000, "wholesale": 900})
    (line,) = price_cart([CartItem(variant.id, 9)])
    assert (line.tier, line.unit_price, line.line_total) == ("retail", Money(1000), Money(9000))


def test_quantity_across_variants_triggers_wholesale_with_each_own_price(product):
    red = make_variant(product, "KS-R", {"retail": 1000, "wholesale": 900}, colour="red")
    blue = make_variant(product, "KS-B", {"retail": 1200, "wholesale": 1100}, colour="blue")
    red_line, blue_line = price_cart([CartItem(red.id, 5), CartItem(blue.id, 5)])
    assert (red_line.tier, red_line.unit_price) == ("wholesale", Money(900))
    assert (blue_line.tier, blue_line.unit_price) == ("wholesale", Money(1100))


def test_empty_cart_is_empty():
    assert price_cart([]) == []


def test_unknown_variant_is_rejected(product):
    with pytest.raises(CatalogError):
        price_cart([CartItem(999999, 1)])


def test_inactive_variant_is_rejected(product):
    variant = make_variant(product, "KS-1", {"retail": 1000})
    Variant.objects.filter(pk=variant.pk).update(is_active=False)
    with pytest.raises(CatalogError):
        price_cart([CartItem(variant.id, 1)])


def test_variant_of_an_inactive_product_is_rejected(product):
    variant = make_variant(product, "KS-1", {"retail": 1000})
    Product.objects.filter(pk=product.pk).update(is_active=False)
    with pytest.raises(CatalogError):
        price_cart([CartItem(variant.id, 1)])


def test_variant_without_a_retail_price_cannot_be_priced(product):
    variant = make_variant(product, "KS-1", {"wholesale": 900})
    with pytest.raises(PricingError):
        price_cart([CartItem(variant.id, 1)])


def test_pricing_uses_two_queries_however_many_items(product, django_assert_max_num_queries):
    variants = [
        make_variant(product, f"KS-{i}", {"retail": 1000, "wholesale": 900}, size=str(i))
        for i in range(8)
    ]
    items = [CartItem(variant.id, 1) for variant in variants]
    with django_assert_max_num_queries(2):
        assert len(price_cart(items)) == 8
