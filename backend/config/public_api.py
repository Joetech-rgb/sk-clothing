"""Helpers for public, read-mostly API views."""

from typing import Any

from django.utils.cache import patch_cache_control
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class PublicView(APIView):
    """No login needed, so no session: no cookie is set and no CSRF check applies."""

    authentication_classes: list[Any] = []
    permission_classes = [AllowAny]


def cached(response: Response, *, seconds: int, stale: int) -> Response:
    """Let Cloudflare keep a successful read for a short while."""
    patch_cache_control(response, public=True, max_age=seconds, stale_while_revalidate=stale)
    return response


def uncached(response: Response) -> Response:
    response["Cache-Control"] = "no-store"
    return response
