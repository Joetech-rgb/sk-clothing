"""Checkout. One public endpoint: POST /api/v1/orders/."""

import re

from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.request import Request
from rest_framework.response import Response

from apps.delivery.fees import DOORSTEP, METHODS, STATION
from apps.identity.origin import check_origin
from apps.identity.phone import InvalidPhone, normalise_ghana_phone
from apps.pricing.money import Money
from config.presenting import money_json
from config.public_api import PublicView, uncached
from config.throttling import AnonThrottle

from . import checkout
from .models import Order
from .throttles import CheckoutThrottle

KEY_SHAPE = re.compile(r"[A-Za-z0-9_-]{8,64}")


class Refusal(APIException):
    """A refusal with a stable machine-readable reason in `details.reason`."""

    reason = ""

    def __init__(self, **details: object) -> None:
        super().__init__()
        self.details = {"reason": self.reason, **details}


class IdempotencyKeyRequired(Refusal):
    status_code = 400
    default_code = "idempotency_key_required"
    default_detail = "Send an Idempotency-Key header of 8 to 64 letters, digits, _ or -."
    reason = "idempotency_key_required"


class IdempotencyConflict(Refusal):
    status_code = 409
    default_code = "idempotency_conflict"
    default_detail = "That Idempotency-Key was already used for a different order."
    reason = "idempotency_conflict"


class InsufficientStock(Refusal):
    status_code = 409
    default_code = "insufficient_stock"
    default_detail = "There is not enough stock for one of the items."
    reason = "insufficient_stock"


class VariantUnavailable(Refusal):
    status_code = 422
    default_code = "variant_unavailable"
    default_detail = "One of the items is not available."
    reason = "variant_unavailable"


class CodNotAvailable(Refusal):
    status_code = 400
    default_code = "cod_not_available"
    default_detail = "Pay on delivery is not available for this delivery choice."
    reason = "cod_not_available"


class TooManyOpenOrders(Refusal):
    status_code = 429
    default_code = "too_many_open_orders"
    default_detail = "You have several unpaid orders. Pay for one, or wait a few minutes."
    reason = "too_many_open_orders"


class ItemSerializer(serializers.Serializer):
    variant_id = serializers.IntegerField(min_value=1)
    quantity = serializers.IntegerField(min_value=1, max_value=1000)


class DeliverySerializer(serializers.Serializer):
    method = serializers.ChoiceField(choices=sorted(METHODS))
    station_name = serializers.CharField(max_length=100, required=False)
    latitude = serializers.FloatField(min_value=-90, max_value=90, required=False)
    longitude = serializers.FloatField(min_value=-180, max_value=180, required=False)
    address = serializers.CharField(max_length=300, required=False, allow_blank=True)

    def validate(self, attrs: dict) -> dict:
        method = attrs["method"]
        if method == STATION and not attrs.get("station_name", "").strip():
            raise ValidationError({"station_name": "Choose a station."})
        if method == DOORSTEP:
            if "latitude" not in attrs or "longitude" not in attrs:
                raise ValidationError({"latitude": "Pin the delivery location on the map."})
            if not attrs.get("address", "").strip():
                raise ValidationError({"address": "Enter the delivery address."})
        return attrs


class CheckoutSerializer(serializers.Serializer):
    items = serializers.ListField(child=ItemSerializer(), min_length=1, max_length=50)
    delivery = DeliverySerializer()
    contact_name = serializers.CharField(max_length=120)
    contact_phone = serializers.CharField(max_length=32)
    payment_method = serializers.ChoiceField(choices=["online", "cod"], default="online")


def _order_json(result: checkout.CheckoutResult) -> dict:
    order: Order = result.order
    fee = order.delivery_fee_pesewas
    total = order.total_pesewas
    return {
        "reference": order.reference,
        "replayed": not result.created,
        "payment_status": order.payment,
        "fulfilment_status": order.fulfilment,
        "refund_status": order.refund,
        "pickup": order.pickup,
        "delivery_method": order.delivery_method,
        "subtotal": money_json(Money(order.subtotal_pesewas)),
        "delivery_fee": None if fee is None else money_json(Money(fee)),
        "total": None if total is None else money_json(Money(total)),
        "lines": [
            {
                "variant_id": line.variant_id,
                "name": line.name,
                "quantity": line.quantity,
                "tier": line.tier,
                "unit_price": money_json(Money(line.unit_price_pesewas)),
                "line_total": money_json(Money(line.line_total_pesewas)),
            }
            for line in order.lines.all()
        ],
        "stock_held_until": result.reservation_expires_at,
        "created_at": order.created_at,
    }


class SessionWithoutCsrfToken(SessionAuthentication):
    """Recognises a signed-in customer from the session cookie. The Origin check in
    CheckoutView.initial() stands in for the CSRF token, as on the login endpoints."""

    def enforce_csrf(self, request: Request) -> None:
        return None


class CheckoutView(PublicView):
    """Guests and signed-in customers both use it. The Origin check stands in for a CSRF token."""

    authentication_classes = [SessionWithoutCsrfToken]
    throttle_classes = [AnonThrottle, CheckoutThrottle]

    def initial(self, request: Request, *args: object, **kwargs: object) -> None:
        check_origin(request)
        super().initial(request, *args, **kwargs)

    @extend_schema(request=CheckoutSerializer, responses={201: None, 200: None})
    def post(self, request: Request) -> Response:
        key = request.headers.get("Idempotency-Key", "")
        if not KEY_SHAPE.fullmatch(key):
            raise IdempotencyKeyRequired
        body = CheckoutSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        try:
            phone = normalise_ghana_phone(data["contact_phone"])
        except InvalidPhone as error:
            raise ValidationError({"contact_phone": "Enter a valid Ghana phone number."}) from error
        delivery = data["delivery"]
        user = request.user
        user_id = user.pk if user.is_authenticated and user.is_active else None
        spec = checkout.CheckoutRequest(
            items=checkout.merge_items([(i["variant_id"], i["quantity"]) for i in data["items"]]),
            delivery_method=delivery["method"],
            contact_name=data["contact_name"],
            contact_phone=phone,
            pay_on_delivery=data["payment_method"] == "cod",
            station_name=delivery.get("station_name"),
            latitude=delivery.get("latitude"),
            longitude=delivery.get("longitude"),
            address=delivery.get("address", ""),
        )
        if any(quantity > 1000 for _, quantity in spec.items):
            raise ValidationError({"items": "At most 1000 of one item."})
        try:
            result = checkout.checkout(spec, idempotency_key=key, user_id=user_id)
        except checkout.VariantUnavailable as error:
            raise VariantUnavailable(variant_id=error.variant_id) from error
        except checkout.OutOfStock as error:
            raise InsufficientStock(
                variant_id=error.variant_id, available=error.available
            ) from error
        except checkout.CodNotAvailable as error:
            raise CodNotAvailable from error
        except checkout.IdempotencyMismatch as error:
            raise IdempotencyConflict from error
        except checkout.TooManyOpenOrders as error:
            raise TooManyOpenOrders from error
        except checkout.BadDelivery as error:
            raise ValidationError({"delivery": str(error)}) from error
        response = Response(_order_json(result), status=201 if result.created else 200)
        return uncached(response)
