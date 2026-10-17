import pytest
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from apps.catalog.models import Category, PriceTier, Product, Variant
from apps.pricing.services import TIER_NAMES


@pytest.fixture
def product(db):
    category = Category.objects.create(name="Shirts", slug="shirts")
    return Product.objects.create(name="Kente shirt", slug="kente-shirt", category=category)


def test_tier_choices_match_the_pricing_tiers():
    assert set(PriceTier.Tier.values) == set(TIER_NAMES)


def test_sku_is_unique(product):
    Variant.objects.create(product=product, sku="KS-1", size="M")
    with pytest.raises(IntegrityError), transaction.atomic():
        Variant.objects.create(product=product, sku="KS-1", size="L")


def test_same_size_and_colour_cannot_repeat_on_a_product(product):
    Variant.objects.create(product=product, sku="KS-1", size="M", colour="red")
    with pytest.raises(IntegrityError), transaction.atomic():
        Variant.objects.create(product=product, sku="KS-2", size="M", colour="red")


def test_one_price_per_variant_per_tier(product):
    variant = Variant.objects.create(product=product, sku="KS-1")
    PriceTier.objects.create(variant=variant, tier="retail", price_pesewas=1000)
    with pytest.raises(IntegrityError), transaction.atomic():
        PriceTier.objects.create(variant=variant, tier="retail", price_pesewas=900)


def test_database_refuses_a_negative_price(product):
    variant = Variant.objects.create(product=product, sku="KS-1")
    with pytest.raises(IntegrityError), transaction.atomic():
        PriceTier.objects.create(variant=variant, tier="retail", price_pesewas=-1)


def test_slug_is_unique(product):
    with pytest.raises(IntegrityError), transaction.atomic():
        Product.objects.create(name="Other", slug="kente-shirt", category=product.category)


def test_a_category_with_products_cannot_be_deleted(product):
    with pytest.raises(ProtectedError):
        product.category.delete()
