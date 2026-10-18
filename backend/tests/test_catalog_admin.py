from decimal import Decimal

import pytest

from apps.catalog.forms import PriceTierForm
from apps.catalog.models import Category, PriceTier, Product, Variant


@pytest.fixture
def product(db):
    category = Category.objects.create(name="Shirts", slug="shirts")
    return Product.objects.create(name="Kente shirt", slug="kente-shirt", category=category)


def _variant_post(product, tiers):
    data = {
        "product": product.id,
        "sku": "KS-1",
        "size": "M",
        "colour": "red",
        "is_active": "on",
        "tiers-TOTAL_FORMS": str(len(tiers)),
        "tiers-INITIAL_FORMS": "0",
        "tiers-MIN_NUM_FORMS": "0",
        "tiers-MAX_NUM_FORMS": "4",
    }
    for index, (tier, price) in enumerate(tiers):
        data[f"tiers-{index}-id"] = ""
        data[f"tiers-{index}-variant"] = ""
        data[f"tiers-{index}-tier"] = tier
        data[f"tiers-{index}-price_ghs"] = price
    return data


@pytest.mark.django_db
def test_form_converts_cedis_to_pesewas():
    form = PriceTierForm(data={"tier": "retail", "price_ghs": "12.50"})
    assert form.is_valid(), form.errors
    assert form.instance.price_pesewas == 1250


@pytest.mark.django_db
def test_form_rejects_three_decimals_and_negatives():
    assert not PriceTierForm(data={"tier": "retail", "price_ghs": "12.505"}).is_valid()
    assert not PriceTierForm(data={"tier": "retail", "price_ghs": "-1"}).is_valid()


@pytest.mark.django_db
def test_form_shows_existing_price_in_cedis(product):
    variant = Variant.objects.create(product=product, sku="KS-1")
    tier = PriceTier.objects.create(variant=variant, tier="retail", price_pesewas=1250)
    form = PriceTierForm(instance=tier)
    assert form.fields["price_ghs"].initial == Decimal("12.50")


@pytest.mark.django_db
def test_admin_pages_load(admin_client, product):
    variant = Variant.objects.create(product=product, sku="KS-1")
    for url in (
        "/admin/catalog/category/",
        "/admin/catalog/category/add/",
        "/admin/catalog/product/",
        "/admin/catalog/product/add/",
        f"/admin/catalog/product/{product.id}/change/",
        "/admin/catalog/variant/",
        "/admin/catalog/variant/add/",
        f"/admin/catalog/variant/{variant.id}/change/",
    ):
        assert admin_client.get(url).status_code == 200, url


@pytest.mark.django_db
def test_admin_creates_a_variant_with_prices(admin_client, product):
    post = _variant_post(product, [("retail", "12.50"), ("wholesale", "10.00")])
    response = admin_client.post("/admin/catalog/variant/add/", post)
    assert response.status_code == 302
    prices = dict(PriceTier.objects.values_list("tier", "price_pesewas"))
    assert prices == {"retail": 1250, "wholesale": 1000}


@pytest.mark.django_db
def test_admin_refuses_a_variant_without_a_retail_price(admin_client, product):
    post = _variant_post(product, [("wholesale", "10.00")])
    response = admin_client.post("/admin/catalog/variant/add/", post)
    assert response.status_code == 200
    assert b"Every variant needs a retail price" in response.content
    assert Variant.objects.count() == 0


@pytest.mark.django_db
def test_admin_refuses_the_same_tier_twice(admin_client, product):
    post = _variant_post(product, [("retail", "12.50"), ("retail", "11.00")])
    response = admin_client.post("/admin/catalog/variant/add/", post)
    assert response.status_code == 200
    assert Variant.objects.count() == 0
