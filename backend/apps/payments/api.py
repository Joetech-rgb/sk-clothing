"""The payment endpoints the storefront calls. Guests and signed-in customers both use them.

POST /api/v1/payments/initialize/  start paying for an order, get the Paystack page to send the
                                   customer to
GET  /api/v1/payments/verify/      the page Paystack returns the customer to calls this; the
                                   server asks Paystack what happened and answers with the order's
                                   statuses
"""

from django.conf import settings
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import APIException
from rest_framework.request import Request
from rest_framework.response import Response

from apps.identity.origin import check_origin
from apps.orders import settlement
from config.public_api import PublicView, uncached
from config.throttling import AnonThrottle

from . import confirm
from .client import PaystackError, ProviderNotConfigured, get_paystack_client


class Refusal(APIException):
    reason = ""

    def __init__(self, **details: object) -> None:
        super().__init__()
        self.details = {"reason": self.reason, **details}


class OrderNotFound(Refusal):
    status_code = 404
    default_code = "order_not_found"
    default_detail = "We could not find that order."
    reason = "order_not_found"


class OrderNotPayable(Refusal):
    status_code = 409
    default_code = "order_not_payable"
    default_detail = "This order cannot be paid for right now."
    reason = "order_not_payable"


class TooManyPaymentAttempts(Refusal):
    status_code = 429
    default_code = "too_many_payment_attempts"
    default_detail = "Too many payment attempts for this order. Please contact us."
    reason = "too_many_payment_attempts"


class PaymentUnavailable(Refusal):
    status_code = 503
    default_code = "payment_unavailable"
    default_detail = "We cannot reach the payment service right now. Please try again shortly."
    reason = "payment_unavailable"


class UnknownReference(Refusal):
    status_code = 404
    default_code = "unknown_reference"
    default_detail = "We could not find that payment."
    reason = "unknown_reference"


class StartThrottle(AnonThrottle):
    scope = "payment_start_ip"

    def get_rate(self) -> str:
        return str(confirm.limit("start_ip_rate"))


class VerifyThrottle(AnonThrottle):
    scope = "payment_verify_ip"

    def get_rate(self) -> str:
        return str(confirm.limit("verify_ip_rate"))


class InitializeSerializer(serializers.Serializer):
    order_reference = serializers.CharField(max_length=24)
    email = serializers.EmailField(max_length=254)


class InitializeView(PublicView):
    throttle_classes = [AnonThrottle, StartThrottle]

    def initial(self, request: Request, *args: object, **kwargs: object) -> None:
        check_origin(request)
        super().initial(request, *args, **kwargs)

    @extend_schema(request=InitializeSerializer, responses={200: None})
    def post(self, request: Request) -> Response:
        body = InitializeSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            result = confirm.start_payment(
                body.validated_data["order_reference"].strip(),
                body.validated_data["email"].strip().lower(),
                client=get_paystack_client(),
                callback_url=getattr(settings, "PAYSTACK_CALLBACK_URL", None) or None,
            )
        except settlement.OrderNotFound as error:
            raise OrderNotFound from error
        except settlement.NotPayable as error:
            raise OrderNotPayable(why=error.why) from error
        except confirm.TooManyAttempts as error:
            raise TooManyPaymentAttempts from error
        except (PaystackError, ProviderNotConfigured) as error:
            raise PaymentUnavailable from error
        return uncached(
            Response({"authorization_url": result.authorization_url, "reference": result.reference})
        )


class VerifyView(PublicView):
    throttle_classes = [AnonThrottle, VerifyThrottle]

    @extend_schema(responses={200: None})
    def get(self, request: Request) -> Response:
        reference = request.query_params.get("reference", "").strip()
        if not reference or len(reference) > 100:
            raise UnknownReference
        try:
            result = confirm.confirm_reference(reference, client=get_paystack_client())
        except (PaystackError, ProviderNotConfigured) as error:
            raise PaymentUnavailable from error
        if result.outcome == confirm.UNKNOWN_REFERENCE or result.order_id is None:
            raise UnknownReference
        summary = settlement.order_summary(result.order_id)
        if summary is None:
            raise UnknownReference
        return uncached(Response({"outcome": result.outcome, **summary}))
