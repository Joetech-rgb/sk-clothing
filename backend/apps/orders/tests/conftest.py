from dataclasses import dataclass

import pytest
from django.core.cache import cache

from apps.catalog.models import Category, PriceTier, Product, Variant
from apps.delivery.models import DeliverySettings, Station
from apps.inventory import services as inventory


@dataclass
class Shop:
    shirt: int  # variant ids
    shoe: int
    cap: int  # stocked, but the product is switched off
    scarce: int  # one unit in stock
    empty: int  # no stock


def make_variant(product, sku, price, *, stock, size="", colour="", active=True):
    variant = Variant.objects.create(
        product=product, sku=sku, size=size, colour=colour, is_active=active
    )
    PriceTier.objects.create(variant=variant, tier="retail", price_pesewas=price)
    if stock:
        inventory.receive_stock(variant.pk, stock, idempotency_key=f"seed-{sku}")
    return variant.pk


@pytest.fixture(autouse=True)
def checkout_environment(settings):
    settings.CSRF_TRUSTED_ORIGINS = ["https://www.example-shop.test"]
    settings.CHECKOUT_LIMITS = {"checkout_ip_rate": "10000/hour", "open_orders_per_phone": 100}
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def shop(db):
    category = Category.objects.create(name="Clothes", slug="clothes")
    shirts = Product.objects.create(name="Red shirt", slug="red-shirt", category=category)
    shoes = Product.objects.create(name="Sneakers", slug="sneakers", category=category)
    caps = Product.objects.create(name="Cap", slug="cap", category=category, is_active=False)
    DeliverySettings.objects.create(
        shop_latitude="5.603700",
        shop_longitude="-0.187000",
        minimum_fee_pesewas=1000,
        base_fee_pesewas=500,
        rate_per_km_pesewas=200,
        max_distance_km="30.00",
        road_factor="1.30",
    )
    Station.objects.create(name="Kumasi STC", fee_pesewas=2500)
    return Shop(
        shirt=make_variant(shirts, "SHIRT-M-RED", 5000, stock=10, size="M", colour="Red"),
        shoe=make_variant(shoes, "SHOE-42", 12000, stock=4, size="42"),
        cap=make_variant(caps, "CAP-1", 900, stock=5),
        scarce=make_variant(shirts, "SHIRT-L-RED", 5000, stock=1, size="L", colour="Red"),
        empty=make_variant(shoes, "SHOE-43", 12000, stock=0, size="43"),
    )
