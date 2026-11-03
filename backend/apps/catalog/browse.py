"""Reads for the storefront: categories, product pages, product details.

Business rules stay in the services. This module only gathers rows and hands them to the pure
presenters. A list page costs a fixed handful of queries however many products it holds.
"""

from collections import defaultdict
from collections.abc import Sequence
from typing import Any

from django.conf import settings
from django.db.models import Prefetch, QuerySet

from apps.inventory.services import available
from apps.pricing.money import Money

from .media_keys import public_url
from .models import Category, Product, Variant
from .presenters import money_json, price_from, quantity_rules, tier_rows
from .search import SearchRequest
from .search_backend import get_search_service
from .tree import with_descendants


def _tiers(variant: Variant) -> dict[str, Money]:
    return {tier.tier: Money(tier.price_pesewas) for tier in variant.tiers.all()}


def _with_relations(queryset: QuerySet[Product]) -> QuerySet[Product]:
    return queryset.select_related("category").prefetch_related(
        "images",
        Prefetch(
            "variants", queryset=Variant.objects.filter(is_active=True).prefetch_related("tiers")
        ),
    )


def _sellable_variants(product: Product) -> list[Variant]:
    return [variant for variant in product.variants.all() if "retail" in _tiers(variant)]


def _image(product: Product) -> dict[str, Any] | None:
    first = next(iter(product.images.all()), None)
    if first is None:
        return None
    url = public_url(settings.MEDIA_BASE_URL, first.storage_key)
    return {"url": url, "alt_text": first.alt_text}


def _category_ref(product: Product) -> dict[str, Any]:
    category = product.category
    return {"id": category.pk, "name": category.name, "slug": category.slug}


def list_categories() -> list[dict[str, Any]]:
    rows = Category.objects.filter(is_active=True).order_by("position", "name")
    return [
        {"id": c.pk, "name": c.name, "slug": c.slug, "parent_id": c.parent_id} for c in rows
    ]


def category_ids(slug: str) -> tuple[int, ...]:
    """A category and everything under it. An unknown or inactive slug gives no categories, so
    the page is simply empty rather than an error."""
    category = Category.objects.filter(slug=slug, is_active=True).first()
    if category is None:
        return ()
    children: dict[int | None, list[int]] = defaultdict(list)
    active = Category.objects.filter(is_active=True).values_list("id", "parent_id")
    for child_id, parent_id in active:
        children[parent_id].append(child_id)
    return tuple(sorted(with_descendants(children, category.pk)))


def _hydrate(ids: Sequence[int]) -> list[Product]:
    found = {p.pk: p for p in _with_relations(Product.objects.filter(id__in=ids, is_active=True))}
    return [found[i] for i in ids if i in found]


def _list_item(product: Product, stock: dict[int, int]) -> dict[str, Any]:
    variants = _sellable_variants(product)
    tiers = [_tiers(v) for v in variants]
    lowest = price_from(tiers)
    return {
        "id": product.pk,
        "name": product.name,
        "slug": product.slug,
        "category": _category_ref(product),
        "image": _image(product),
        "price_from": money_json(lowest) if lowest is not None else None,
        "in_stock": any(stock.get(v.pk, 0) > 0 for v in variants),
        "has_wholesale": any("wholesale" in t for t in tiers),
    }


def product_page(request: SearchRequest) -> dict[str, Any]:
    page = get_search_service().search(request)
    products = _hydrate(page.product_ids)
    stock = available([v.pk for p in products for v in p.variants.all()])
    return {
        "results": [_list_item(p, stock) for p in products],
        "next_cursor": page.next_cursor,
    }


def product_detail(slug: str) -> dict[str, Any] | None:
    product = _with_relations(
        Product.objects.filter(slug=slug, is_active=True, category__is_active=True)
    ).first()
    if product is None:
        return None
    variants = _sellable_variants(product)
    if not variants:
        return None
    stock = available([v.pk for v in variants])
    tiers = {v.pk: _tiers(v) for v in variants}
    lowest = price_from(tiers.values())
    return {
        "id": product.pk,
        "name": product.name,
        "slug": product.slug,
        "description": product.description,
        "category": _category_ref(product),
        "images": [
            {"url": public_url(settings.MEDIA_BASE_URL, i.storage_key), "alt_text": i.alt_text}
            for i in product.images.all()
        ],
        "price_from": money_json(lowest) if lowest is not None else None,
        "quantity_rules": quantity_rules(tiers.values()),
        "variants": [
            {
                "id": v.pk,
                "sku": v.sku,
                "size": v.size,
                "colour": v.colour,
                "available": stock.get(v.pk, 0),
                "in_stock": stock.get(v.pk, 0) > 0,
                "tiers": tier_rows(tiers[v.pk]),
            }
            for v in variants
        ],
    }
