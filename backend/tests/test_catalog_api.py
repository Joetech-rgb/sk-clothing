import base64
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.catalog.models import Category, PriceTier, Product, ProductImage, Variant
from apps.inventory.services import receive_stock

LIST = "/api/v1/catalog/products/"
PRICE = "/api/v1/catalog/price/"


@pytest.fixture
def shirts(db):
    return Category.objects.create(name="Shirts", slug="shirts")


def make_product(category, name, *, slug=None, retail=1000, wholesale=None, stock=0, **fields):
    slug = slug or name.lower().replace(" ", "-")
    product = Product.objects.create(name=name, slug=slug, category=category, **fields)
    variant = Variant.objects.create(product=product, sku=f"{slug}-1", size="M")
    if retail is not None:
        PriceTier.objects.create(variant=variant, tier="retail", price_pesewas=retail)
    if wholesale is not None:
        PriceTier.objects.create(variant=variant, tier="wholesale", price_pesewas=wholesale)
    if stock:
        receive_stock(variant.id, stock, idempotency_key=f"stock-{slug}")
    return product, variant


def ids(response):
    return [item["id"] for item in response.json()["results"]]


# --- categories ----------------------------------------------------------------------------


def test_categories_list_active_ones_and_may_be_cached(client, shirts):
    Category.objects.create(name="Hidden", slug="hidden", is_active=False)
    Category.objects.create(name="Polo", slug="polo", parent=shirts, position=1)
    response = client.get("/api/v1/catalog/categories/")
    assert response.status_code == 200
    body = response.json()
    assert [c["slug"] for c in body] == ["shirts", "polo"]  # by position, then name
    assert "hidden" not in [c["slug"] for c in body]
    polo = next(c for c in body if c["slug"] == "polo")
    assert polo["parent_id"] == shirts.id
    assert "public" in response["Cache-Control"] and "max-age=300" in response["Cache-Control"]


# --- the list ----------------------------------------------------------------------------------


def test_a_product_list_is_public_and_sets_no_cookie(client, shirts):
    make_product(shirts, "Kente Shirt", stock=5)
    response = client.get(LIST)
    assert response.status_code == 200
    assert not response.cookies
    assert "public" in response["Cache-Control"]
    item = response.json()["results"][0]
    assert item["name"] == "Kente Shirt" and item["in_stock"] is True
    assert item["price_from"] == {"pesewas": 1000, "display": "GHS 10.00"}
    assert item["category"]["slug"] == "shirts"


def test_products_that_cannot_be_bought_are_not_listed(client, shirts):
    make_product(shirts, "Visible")
    make_product(shirts, "No Retail Price", retail=None, wholesale=900)
    make_product(shirts, "Switched Off", is_active=False)
    hidden = Category.objects.create(name="Off", slug="off", is_active=False)
    make_product(hidden, "In Hidden Category")
    inactive_variant, _ = make_product(shirts, "Only Inactive Variant")
    Variant.objects.filter(product=inactive_variant).update(is_active=False)
    names = [i["name"] for i in client.get(LIST).json()["results"]]
    assert names == ["Visible"]


def test_in_stock_reflects_what_can_be_sold_right_now(client, shirts):
    make_product(shirts, "Has Stock", stock=3)
    make_product(shirts, "No Stock")
    items = {i["name"]: i["in_stock"] for i in client.get(LIST).json()["results"]}
    assert items == {"Has Stock": True, "No Stock": False}


def test_wholesale_availability_is_flagged(client, shirts):
    make_product(shirts, "With Wholesale", wholesale=900)
    make_product(shirts, "Retail Only")
    flags = {i["name"]: i["has_wholesale"] for i in client.get(LIST).json()["results"]}
    assert flags == {"With Wholesale": True, "Retail Only": False}


def test_sorting_by_price_and_newest(client, shirts):
    cheap, _ = make_product(shirts, "Cheap", retail=500)
    mid, _ = make_product(shirts, "Mid", retail=1500)
    dear, _ = make_product(shirts, "Dear", retail=3000)
    Product.objects.filter(pk=cheap.pk).update(created_at=timezone.now() - timedelta(days=3))
    Product.objects.filter(pk=mid.pk).update(created_at=timezone.now() - timedelta(days=2))
    assert ids(client.get(LIST, {"sort": "price_low"})) == [cheap.id, mid.id, dear.id]
    assert ids(client.get(LIST, {"sort": "price_high"})) == [dear.id, mid.id, cheap.id]
    assert ids(client.get(LIST, {"sort": "newest"})) == [dear.id, mid.id, cheap.id]


def test_a_products_lowest_active_retail_price_is_what_it_sorts_by(client, shirts):
    product, first = make_product(shirts, "Two Sizes", retail=2000)
    second = Variant.objects.create(product=product, sku="two-sizes-2", size="L")
    PriceTier.objects.create(variant=second, tier="retail", price_pesewas=800)
    other, _ = make_product(shirts, "Other", retail=1000)
    assert ids(client.get(LIST, {"sort": "price_low"})) == [product.id, other.id]
    Variant.objects.filter(pk=second.pk).update(is_active=False)  # the cheap size is withdrawn
    assert ids(client.get(LIST, {"sort": "price_low"})) == [other.id, product.id]


def test_filtering_by_category_includes_its_sub_categories(client, shirts):
    polo = Category.objects.create(name="Polo", slug="polo", parent=shirts)
    trousers = Category.objects.create(name="Trousers", slug="trousers")
    a, _ = make_product(shirts, "Plain Shirt")
    b, _ = make_product(polo, "Polo Shirt")
    c, _ = make_product(trousers, "Chinos")
    assert sorted(ids(client.get(LIST, {"category": "shirts"}))) == sorted([a.id, b.id])
    assert ids(client.get(LIST, {"category": "polo"})) == [b.id]
    assert ids(client.get(LIST, {"category": "trousers"})) == [c.id]
    assert ids(client.get(LIST, {"category": "no-such-category"})) == []


def test_pages_follow_the_cursor_without_repeats_or_gaps(client, shirts):
    made = [make_product(shirts, f"Item {n}", slug=f"item-{n}")[0] for n in range(5)]
    seen, cursor = [], None
    for _ in range(5):
        params = {"limit": 2, **({"cursor": cursor} if cursor else {})}
        body = client.get(LIST, params).json()
        seen.extend(i["id"] for i in body["results"])
        cursor = body["next_cursor"]
        if cursor is None:
            break
    assert sorted(seen) == sorted(p.id for p in made) and len(seen) == len(set(seen)) == 5
    assert cursor is None


def test_bad_query_parameters_are_a_validation_error(client, shirts):
    for params in (
        {"limit": 0},
        {"limit": 51},
        {"limit": "abc"},
        {"sort": "random"},
        {"cursor": "not-a-cursor"},
        {"cursor": base64.urlsafe_b64encode(b"o:99999999").decode()},
    ):
        response = client.get(LIST, params)
        assert response.status_code == 400, params
        assert response.json()["error"]["code"] == "validation_error"


def test_a_list_page_costs_a_fixed_handful_of_queries(
    client, shirts, django_assert_max_num_queries
):
    for n in range(20):
        product, variant = make_product(shirts, f"Bulk {n}", slug=f"bulk-{n}", stock=2)
        second = Variant.objects.create(product=product, sku=f"bulk-{n}-b", size="L")
        PriceTier.objects.create(variant=second, tier="retail", price_pesewas=1100)
        ProductImage.objects.create(product=product, storage_key=f"media/{n}.webp")
    with django_assert_max_num_queries(8):
        response = client.get(LIST, {"limit": 20})
    assert len(response.json()["results"]) == 20


def test_product_images_use_the_media_base_url(client, shirts, settings):
    settings.MEDIA_BASE_URL = "https://cdn.example.com/"
    product, _ = make_product(shirts, "Pictured")
    ProductImage.objects.create(product=product, storage_key="media/a.webp", alt_text="Front")
    item = client.get(LIST).json()["results"][0]
    assert item["image"] == {"url": "https://cdn.example.com/media/a.webp", "alt_text": "Front"}


# --- search -----------------------------------------------------------------------------------


def test_search_finds_products_by_name_and_description(client, shirts):
    kente, _ = make_product(shirts, "Kente Shirt")
    plain, _ = make_product(shirts, "Plain Shirt", description="Woven in a kente pattern")
    other, _ = make_product(shirts, "Denim Jacket")
    found = ids(client.get(LIST, {"q": "kente"}))
    assert set(found) == {kente.id, plain.id} and other.id not in found


def test_a_name_match_ranks_above_a_description_match(client, shirts):
    in_description, _ = make_product(shirts, "Plain Shirt", description="A kente pattern")
    in_name, _ = make_product(shirts, "Kente Shirt")
    assert ids(client.get(LIST, {"q": "kente"})) == [in_name.id, in_description.id]


def test_search_forgives_a_mistyped_letter(client, shirts):
    kente, _ = make_product(shirts, "Kente Cloth Shirt")
    make_product(shirts, "Denim Jacket")
    assert ids(client.get(LIST, {"q": "kenta"})) == [kente.id]


def test_search_with_no_match_is_empty_and_hostile_input_is_harmless(client, shirts):
    make_product(shirts, "Kente Shirt")
    assert ids(client.get(LIST, {"q": "zzzzqqqq"})) == []
    for q in ("'; DROP TABLE catalog_product; --", "a & | ! ( )", "x" * 500, "\x00\x1b[31m"):
        assert client.get(LIST, {"q": q}).status_code in (200, 400)


def test_search_respects_the_category_and_sort_filters(client, shirts):
    polo = Category.objects.create(name="Polo", slug="polo")
    a, _ = make_product(shirts, "Kente Shirt", retail=2000)
    b, _ = make_product(polo, "Kente Polo", retail=1000)
    assert ids(client.get(LIST, {"q": "kente", "category": "polo"})) == [b.id]
    assert ids(client.get(LIST, {"q": "kente", "sort": "price_low"})) == [b.id, a.id]


# --- the product page ----------------------------------------------------------------------


def test_a_product_page_shows_only_filled_tiers_and_the_stock_left(client, shirts):
    product, variant = make_product(
        shirts, "Kente Shirt", wholesale=900, stock=7, description="Hand woven"
    )
    response = client.get(f"/api/v1/catalog/products/{product.slug}/")
    assert response.status_code == 200 and "max-age=30" in response["Cache-Control"]
    body = response.json()
    assert body["description"] == "Hand woven"
    assert body["quantity_rules"] == [{"tier": "wholesale", "min_quantity": 10}]
    (shown,) = body["variants"]
    assert (shown["sku"], shown["available"], shown["in_stock"]) == (variant.sku, 7, True)
    assert [(t["tier"], t["min_quantity"]) for t in shown["tiers"]] == [
        ("retail", 1),
        ("wholesale", 10),
    ]
    assert shown["tiers"][1]["price"]["pesewas"] == 900


def test_stock_left_does_not_count_what_other_shoppers_are_holding(client, shirts):
    from apps.inventory.services import StockRequest, reserve_many

    product, variant = make_product(shirts, "Kente Shirt", stock=5)
    reserve_many([StockRequest(variant.id, 2)], idempotency_key="someone-else")
    body = client.get(f"/api/v1/catalog/products/{product.slug}/").json()
    assert body["variants"][0]["available"] == 3


def test_withdrawn_or_unsellable_variants_are_hidden(client, shirts):
    product, first = make_product(shirts, "Kente Shirt")
    off = Variant.objects.create(product=product, sku="off", size="S", is_active=False)
    PriceTier.objects.create(variant=off, tier="retail", price_pesewas=1)
    no_price = Variant.objects.create(product=product, sku="noprice", size="XL")
    PriceTier.objects.create(variant=no_price, tier="wholesale", price_pesewas=1)
    body = client.get(f"/api/v1/catalog/products/{product.slug}/").json()
    assert [v["sku"] for v in body["variants"]] == [first.sku]


def test_a_product_that_is_not_for_sale_is_a_404_in_the_standard_envelope(client, shirts):
    make_product(shirts, "Switched Off", is_active=False)
    for slug in ("switched-off", "never-existed"):
        response = client.get(f"/api/v1/catalog/products/{slug}/")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"


# --- pricing a basket ----------------------------------------------------------------------------


def post_price(client, items):
    return client.post(PRICE, {"items": items}, content_type="application/json")


def test_quantity_across_variants_unlocks_the_wholesale_price(client, shirts):
    product, red = make_product(shirts, "Kente Shirt", retail=1000, wholesale=900)
    blue = Variant.objects.create(product=product, sku="blue", colour="blue")
    PriceTier.objects.create(variant=blue, tier="retail", price_pesewas=1200)
    PriceTier.objects.create(variant=blue, tier="wholesale", price_pesewas=1100)
    response = post_price(
        client, [{"variant_id": red.id, "quantity": 5}, {"variant_id": blue.id, "quantity": 5}]
    )
    assert response.status_code == 200 and response["Cache-Control"] == "no-store"
    body = response.json()
    assert [(x["tier"], x["unit_price"]["pesewas"]) for x in body["lines"]] == [
        ("wholesale", 900),
        ("wholesale", 1100),
    ]
    assert body["lines"][0]["line_total"]["pesewas"] == 4500
    assert body["subtotal"] == {"pesewas": 10000, "display": "GHS 100.00"}
    assert body["lines"][0]["discounts"] == []


def test_a_client_can_never_name_its_own_price(client, shirts):
    _, variant = make_product(shirts, "Kente Shirt", retail=1000)
    for extra in ({"unit_price": 1}, {"price": 1}, {"tier": "bulk"}, {"discount": 99}):
        response = post_price(client, [{"variant_id": variant.id, "quantity": 1, **extra}])
        assert response.status_code == 400, extra
        assert response.json()["error"]["code"] == "validation_error"
    ok = post_price(client, [{"variant_id": variant.id, "quantity": 1}])
    assert ok.json()["lines"][0]["unit_price"]["pesewas"] == 1000


def test_bad_baskets_are_refused(client, shirts):
    _, variant = make_product(shirts, "Kente Shirt")
    for items in (
        [],
        [{"variant_id": variant.id, "quantity": 0}],
        [{"variant_id": variant.id, "quantity": 10001}],
        [{"variant_id": 0, "quantity": 1}],
        [{"variant_id": variant.id, "quantity": 1}, {"variant_id": variant.id, "quantity": 2}],
        [{"variant_id": i + 1, "quantity": 1} for i in range(51)],
        [{"variant_id": variant.id}],
    ):
        assert post_price(client, items).status_code == 400, items
    assert client.post(PRICE, {}, content_type="application/json").status_code == 400


def test_an_unavailable_variant_is_a_422_that_says_which_one(client, shirts):
    product, variant = make_product(shirts, "Kente Shirt")
    Variant.objects.filter(pk=variant.pk).update(is_active=False)
    response = post_price(client, [{"variant_id": variant.id, "quantity": 1}])
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "variant_unavailable"
    assert error["details"] == {"variant_id": variant.id}


def test_a_variant_without_a_retail_price_cannot_be_priced(client, shirts):
    product, variant = make_product(shirts, "No Retail", retail=None, wholesale=900)
    response = post_price(client, [{"variant_id": variant.id, "quantity": 1}])
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "variant_unavailable"


def test_pricing_works_for_a_guest_without_a_session(client, shirts):
    _, variant = make_product(shirts, "Kente Shirt")
    response = post_price(client, [{"variant_id": variant.id, "quantity": 1}])
    assert response.status_code == 200 and not response.cookies
