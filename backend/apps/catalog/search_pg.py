"""PostgreSQL implementation of SearchService (Phase 1A). Replaced by Meilisearch in Phase 1B.

Matches a product when its name or description contains the query words (full-text search with
the 'simple' configuration, so no English stemming gets in the way of Ghanaian product names), or
when its name is close to the query by trigram word similarity, which forgives a mistyped letter.
Only products that can actually be bought are searchable: active, in an active category, with at
least one active variant that has a retail price.
"""

from django.contrib.postgres.search import (
    SearchQuery,
    SearchRank,
    SearchVector,
    TrigramWordSimilarity,
)
from django.db.models import Exists, F, OuterRef, Q, QuerySet, Subquery
from django.db.models.functions import Greatest

from .cursor import decode_cursor, encode_cursor
from .models import PriceTier, Product
from .search import SearchPage, SearchRequest, normalise_query

TRIGRAM_THRESHOLD = 0.4


def _retail_prices() -> QuerySet[PriceTier]:
    return PriceTier.objects.filter(
        variant__product=OuterRef("pk"), variant__is_active=True, tier="retail"
    )


class PostgresSearch:
    def search(self, request: SearchRequest) -> SearchPage:
        offset = decode_cursor(request.cursor)
        queryset = Product.objects.filter(is_active=True, category__is_active=True).filter(
            Exists(_retail_prices())
        )
        if request.category_ids is not None:
            queryset = queryset.filter(category_id__in=request.category_ids)

        query = normalise_query(request.query)
        sort = request.sort
        order: tuple = ("-created_at", "-id")
        if query:
            vector = SearchVector("name", weight="A", config="simple") + SearchVector(
                "description", weight="B", config="simple"
            )
            queryset = queryset.annotate(
                rank=SearchRank(
                    vector, SearchQuery(query, config="simple", search_type="websearch")
                ),
                similarity=TrigramWordSimilarity(query, "name"),
            ).filter(Q(rank__gt=0) | Q(similarity__gt=TRIGRAM_THRESHOLD))
            if sort == "relevance":
                order = (Greatest(F("rank"), F("similarity")).desc(), "-id")
        if sort in ("price_low", "price_high"):
            cheapest = _retail_prices().order_by("price_pesewas").values("price_pesewas")[:1]
            queryset = queryset.annotate(price_from=Subquery(cheapest))
            order = ("price_from", "id") if sort == "price_low" else ("-price_from", "-id")
        elif sort == "newest" or (sort == "relevance" and not query):
            order = ("-created_at", "-id")

        ids = list(
            queryset.order_by(*order).values_list("id", flat=True)[
                offset : offset + request.limit + 1
            ]
        )
        more = len(ids) > request.limit
        return SearchPage(
            product_ids=ids[: request.limit],
            next_cursor=encode_cursor(offset + request.limit) if more else None,
        )
