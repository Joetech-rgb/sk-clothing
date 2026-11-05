"""Checkout. One public endpoint: POST /api/v1/orders/."""

import re

from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from apps.delivery import code_services as delivery_codes
from apps.delivery.fees import DOORSTEP, METHODS, STATION
from apps.identity.origin import check_origin
from apps.identity.phone import InvalidPhone, normalise_ghana_phone
from apps.pricing.money import Money
from config.presenting import money_json
from config.public_api import PublicView, uncached
from config.throttling import AnonThrottle

from . import checkout, lookup, services
from .models import Order
from .states import Fulfilment
from .throttles import CheckoutThrottle, LookupThrottle

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


def _delivery_code_fields(order: Order) -> dict:
    """The delivery code, shown to the customer only while the order is out for delivery."""
    if order.fulfilment != Fulfilment.OUT_FOR_DELIVERY.value:
        return {"delivery_code": None, "delivery_code_locked": False}
    shown = delivery_codes.code_for_display(order.pk)
    return {"delivery_code": shown.code, "delivery_code_locked": shown.locked}


def order_json(order: Order) -> dict:
    """What a customer may see of their order. No keys, internal ids or contact details."""
    fee = order.delivery_fee_pesewas
    total = order.total_pesewas
    return {
        "reference": order.reference,
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
        "created_at": order.created_at,
        **_delivery_code_fields(order),
    }


def _checkout_json(result: checkout.CheckoutResult) -> dict:
    return {
        **order_json(result.order),
        "replayed": not result.created,
        "stock_held_until": result.reservation_expires_at,
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
        response = Response(_checkout_json(result), status=201 if result.created else 200)
        return uncached(response)


class NotFound(Refusal):
    status_code = 404
    default_code = "order_not_found"
    default_detail = "We could not find an order with that reference and phone number."
    reason = "order_not_found"


class LookupSerializer(serializers.Serializer):
    reference = serializers.CharField(max_length=24)
    phone = serializers.CharField(max_length=32)


class OrderLookupView(PublicView):
    """Look an order up again with its reference and the phone number it was placed with."""

    throttle_classes = [AnonThrottle, LookupThrottle]

    @extend_schema(request=LookupSerializer, responses={200: None})
    def post(self, request: Request) -> Response:
        body = LookupSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        order = lookup.find_order(body.validated_data["reference"], body.validated_data["phone"])
        if order is None:
            raise NotFound
        return uncached(Response(order_json(order)))


class DeliveryOrderNotFound(Refusal):
    status_code = 404
    default_code = "order_not_found"
    default_detail = "There is no order with that reference."
    reason = "order_not_found"


class WrongDeliveryCode(Refusal):
    status_code = 400
    default_code = "wrong_code"
    default_detail = "That code is not right."
    reason = "wrong_code"


class MalformedDeliveryCode(Refusal):
    status_code = 400
    default_code = "malformed_code"
    default_detail = "Enter the six-digit code."
    reason = "malformed_code"


class DeliveryCodeLocked(Refusal):
    status_code = 429
    default_code = "code_locked"
    default_detail = "Too many wrong codes. Ask the shop for a new code."
    reason = "code_locked"


class NoDeliveryCode(Refusal):
    status_code = 409
    default_code = "no_delivery_code"
    default_detail = "No delivery code has been issued for this order."
    reason = "no_delivery_code"


class NotOutForDelivery(Refusal):
    status_code = 409
    default_code = "not_out_for_delivery"
    default_detail = "This order is not out for delivery."
    reason = "not_out_for_delivery"


_CONFIRM_REFUSALS = {
    services.ORDER_NOT_FOUND: DeliveryOrderNotFound,
    services.WRONG_CODE: WrongDeliveryCode,
    services.MALFORMED_CODE: MalformedDeliveryCode,
    services.CODE_LOCKED: DeliveryCodeLocked,
    services.NO_DELIVERY_CODE: NoDeliveryCode,
    services.NOT_OUT_FOR_DELIVERY: NotOutForDelivery,
}


class CanConfirmDelivery(BasePermission):
    """Only an account holding the confirm-delivery permission (riders, and staff given it)."""

    def has_permission(self, request: Request, view: object) -> bool:
        return delivery_codes.can_confirm_delivery(request.user)


class ConfirmDeliveryThrottle(UserRateThrottle):
    """A ceiling per signed-in user. The real defence against guessing is the lock on each code."""

    scope = "delivery_confirm"
    rate = "120/hour"


class ConfirmDeliverySerializer(serializers.Serializer):
    code = serializers.CharField(max_length=16)


class ConfirmDeliveryView(APIView):
    """A rider or staff member enters the code the customer shows. Marks the order delivered."""

    authentication_classes = [SessionWithoutCsrfToken]
    permission_classes = [IsAuthenticated, CanConfirmDelivery]
    throttle_classes = [ConfirmDeliveryThrottle]

    def initial(self, request: Request, *args: object, **kwargs: object) -> None:
        check_origin(request)
        super().initial(request, *args, **kwargs)

    @extend_schema(request=ConfirmDeliverySerializer, responses={200: None})
    def post(self, request: Request, reference: str) -> Response:
        body = ConfirmDeliverySerializer(data=request.data)
        body.is_valid(raise_exception=True)
        result = services.confirm_delivery(
            reference, body.validated_data["code"], actor=f"user:{request.user.pk}"
        )
        refusal = _CONFIRM_REFUSALS.get(result.status)
        if refusal is not None:
            raise refusal()
        return uncached(
            Response(
                {
                    "reference": reference,
                    "fulfilment_status": "delivered",
                    "delivered_at": result.delivered_at,
                    "already_delivered": result.status == services.ALREADY_DELIVERED,
                }
            )
        )
