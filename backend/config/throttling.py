from django.conf import settings
from rest_framework.request import Request
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle

from .client_ip import client_ip


class _ClientIPMixin:
    def get_ident(self, request: Request) -> str:
        return client_ip(request.META, trust_cloudflare=settings.TRUST_CLOUDFLARE_HEADERS)


class AnonThrottle(_ClientIPMixin, AnonRateThrottle):
    pass


class UserThrottle(_ClientIPMixin, UserRateThrottle):
    pass
