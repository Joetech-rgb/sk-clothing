"""Public delivery API: the station list for the checkout, and a delivery quote."""

from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response

from config.presenting import money_json
from config.public_api import PublicView, cached, uncached

from .serializers import QuoteRequestSerializer, QuoteResponseSerializer, StationSerializer
from .services import get_quote, station_fees


class StationListView(PublicView):
    @extend_schema(responses=StationSerializer(many=True))
    def get(self, request: Request) -> Response:
        rows = [
            {"name": name, "fee": money_json(fee)}
            for name, fee in sorted(station_fees().items(), key=lambda pair: pair[0].casefold())
        ]
        return cached(Response(StationSerializer(rows, many=True).data), seconds=300, stale=600)


class QuoteView(PublicView):
    """What delivery would cost. The caller sends where to, never a fee."""

    @extend_schema(request=QuoteRequestSerializer, responses=QuoteResponseSerializer)
    def post(self, request: Request) -> Response:
        body = QuoteRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        quote = get_quote(
            data["method"],
            station_name=data.get("station_name"),
            latitude=data.get("latitude"),
            longitude=data.get("longitude"),
        )
        payload = {
            "method": quote.method,
            "status": quote.status,
            "fee": money_json(quote.fee) if quote.fee is not None else None,
            "cod_allowed": quote.cod_allowed,
            "reason": quote.reason,
            "road_km": str(quote.road_km) if quote.road_km is not None else None,
        }
        return uncached(Response(QuoteResponseSerializer(payload).data))
