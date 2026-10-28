"""Login by phone code, logout and "who am I", under /api/v1/auth/."""

from django.contrib.auth import get_user_model
from django.contrib.auth import login as start_session
from django.contrib.auth import logout as end_session
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import APIException, Throttled, ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from config.public_api import PublicView, uncached
from config.throttling import AnonThrottle

from . import login, otp
from .origin import check_origin
from .phone import InvalidPhone
from .throttles import RequestCodeIPThrottle, VerifyCodeIPThrottle


class InvalidCode(APIException):
    status_code = 400
    default_code = "invalid_code"
    default_detail = "That code is not valid. Check it, or ask for a new one."
    details = {"reason": "invalid_code"}


class TooManyAttempts(APIException):
    status_code = 429
    default_code = "too_many_attempts"
    default_detail = "Too many wrong codes. Ask for a new code."
    details = {"reason": "too_many_attempts"}


class SmsUnavailable(APIException):
    status_code = 503
    default_code = "sms_unavailable"
    default_detail = "We cannot send a code right now. Please try again later."
    details = {"reason": "sms_unavailable"}


class RequestCodeSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=32)


class VerifyCodeSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=32)
    code = serializers.CharField(max_length=16)


class _SessionView(PublicView):
    def initial(self, request: Request, *args: object, **kwargs: object) -> None:
        check_origin(request)  # before anything is counted or sent
        super().initial(request, *args, **kwargs)


class RequestCodeView(_SessionView):
    throttle_classes = [AnonThrottle, RequestCodeIPThrottle]

    @extend_schema(request=RequestCodeSerializer, responses={202: None})
    def post(self, request: Request) -> Response:
        body = RequestCodeSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            login.request_code(body.validated_data["phone"])
        except InvalidPhone as error:
            raise ValidationError({"phone": "Enter a valid Ghana phone number."}) from error
        except login.TooSoon as error:
            raise Throttled(wait=error.wait_seconds) from error
        except (login.DailyCapReached, login.SmsUnavailable) as error:
            raise SmsUnavailable from error
        # The same answer whether or not the number has an account, or may use phone login.
        return uncached(Response({"expires_in_seconds": int(otp.TTL.total_seconds())}, status=202))


class VerifyCodeView(_SessionView):
    throttle_classes = [AnonThrottle, VerifyCodeIPThrottle]

    @extend_schema(request=VerifyCodeSerializer, responses={200: None})
    def post(self, request: Request) -> Response:
        body = VerifyCodeSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        result = login.verify_code(body.validated_data["phone"], body.validated_data["code"])
        if result.status == login.LOCKED:
            raise TooManyAttempts
        if result.status != login.OK:
            raise InvalidCode
        user = get_user_model().objects.get(pk=result.user_id)
        # login() starts a fresh session key (and rotates the CSRF token), so a session id that
        # was planted before sign-in is useless afterwards. It also replaces any other user's
        # session on this browser.
        start_session(request._request, user, backend="django.contrib.auth.backends.ModelBackend")
        return uncached(
            Response({"is_new_customer": result.is_new_customer, "user": {"id": user.pk}})
        )


class LogoutView(_SessionView):
    """Ends the session. Safe to call when nobody is signed in. Protected by the Origin check
    rather than a CSRF token, so the storefront needs no token for it; the worst a forged
    request could do is sign a visitor out."""

    throttle_classes = [AnonThrottle]

    @extend_schema(request=None, responses={204: None})
    def post(self, request: Request) -> Response:
        end_session(request._request)
        return uncached(Response(status=204))


class MeView(APIView):
    """Who is signed in. 401 when nobody is, so the storefront can show the login screen."""

    @extend_schema(responses={200: None})
    def get(self, request: Request) -> Response:
        user = request.user
        return uncached(
            Response(
                {
                    "id": user.pk,
                    "full_name": user.full_name,
                    "phone": user.phone,
                    "email": user.email,
                    "is_staff": user.is_staff,
                }
            )
        )
