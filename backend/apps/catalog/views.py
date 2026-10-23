"""The public storefront API for browsing. No login needed, so these views carry no session or
CSRF machinery, and a successful read tells Cloudflare it may keep a copy for a short while."""

from typing import Any

from django.utils.cache import patch_cache_control
from drf_spectacular.utils import extend_schema
from rest_framework.exceptions import APIException, NotFound, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.pricing.money import Money
from apps.pricing.services import PricingError

from . import browse
from .cursor import decode_cursor
from .search import SearchRequest, normalise_query
from .serializers import (
    CategorySerializer,
    PriceRequestSerializer,
    PriceResponseSerializer,
    ProductDetailSerializer,
    ProductListQuerySerializer,
    ProductPageSerializer,
)
from .services import CartItem, CatalogError, price_cart


class VariantUnavailable(APIException):
    status_code = 422
    default_code = "variant_unavailable"
    default_detail = "One of the items is not available."

    def __init__(self, variant_id: int | None = None) -> None:
        super().__init__()
        self.details = {"variant_id": variant_id} if variant_id is not None else None


class PublicView(APIView):
    authentication_classes: list[Any] = []  # no session, so no cookie and no CSRF check
    permission_classes = [AllowAny]


def _cached(response: Response, *, seconds: int, stale: int) -> Response:
    patch_cache_control(
        response, public=True, max_age=seconds, stale_while_revalidate=stale
    )
    return response


class CategoryListView(PublicView):
    @extend_schema(responses=CategorySerializer(many=True))
    def get(self, request: Request) -> Response:
        response = Response(CategorySerializer(browse.list_categories(), many=True).data)
        return _cached(response, seconds=300, stale=600)


class ProductListView(PublicView):
    @extend_schema(parameters=[ProductListQuerySerializer], responses=ProductPageSerializer)
    def get(self, request: Request) -> Response:
        params = ProductListQuerySerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        data = params.validated_data
        try:
            decode_cursor(data.get("cursor"))
        except ValueError as error:
            raise ValidationError({"cursor": "This cursor is not valid."}) from error
        category = data.get("category")
        search = SearchRequest(
            query=normalise_query(data["q"]),
            category_ids=browse.category_ids(category) if category else None,
            sort=data["sort"],
            limit=data["limit"],
            cursor=data.get("cursor") or None,
        )
        response = Response(ProductPageSerializer(browse.product_page(search)).data)
        return _cached(response, seconds=60, stale=120)


class ProductDetailView(PublicView):
    @extend_schema(responses=ProductDetailSerializer)
    def get(self, request: Request, slug: str) -> Response:
        detail = browse.product_detail(slug)
        if detail is None:
            raise NotFound("This product is not available.")
        return _cached(Response(ProductDetailSerializer(detail).data), seconds=30, stale=60)


def _money(money: Money) -> dict[str, Any]:
    return {"pesewas": money.pesewas, "display": str(money)}


class PriceView(PublicView):
    """Prices a basket. The caller sends variant ids and quantities and nothing else: every price
    comes from the database through resolve_price(), so a browser can never name its own price."""

    @extend_schema(request=PriceRequestSerializer, responses=PriceResponseSerializer)
    def post(self, request: Request) -> Response:
        body = PriceRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        items = [
            CartItem(variant_id=i["variant_id"], quantity=i["quantity"])
            for i in body.validated_data["items"]
        ]
        try:
            lines = price_cart(items)
        except CatalogError as error:
            raise VariantUnavailable(error.variant_id) from error
        except PricingError as error:
            raise VariantUnavailable() from error
        subtotal = Money(0)
        for line in lines:
            subtotal = subtotal + line.line_total
        payload = {
            "lines": [
                {
                    "variant_id": line.variant_id,
                    "quantity": line.quantity,
                    "tier": line.tier,
                    "source": line.source,
                    "unit_price": _money(line.unit_price),
                    "line_total": _money(line.line_total),
                    "list_price": _money(line.list_price),
                    "tier_price": _money(line.tier_price),
                    "discounts": [
                        {
                            "discount_id": d.discount_id,
                            "kind": d.kind,
                            "value": d.value,
                            "unit_price_after": _money(d.unit_price_after),
                        }
                        for d in line.discounts
                    ],
                }
                for line in lines
            ],
            "subtotal": _money(subtotal),
        }
        response = Response(PriceResponseSerializer(payload).data)
        response["Cache-Control"] = "no-store"
        return response
