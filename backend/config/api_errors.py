"""DRF exception handler and JSON 404/500 pages, all in the standard envelope."""

import math
from typing import Any

from django.http import HttpRequest, JsonResponse
from rest_framework.exceptions import NotAuthenticated, Throttled, ValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from .envelope import STATUS_CODES, build_error, code_for_status, plain
from .request_ids import NO_REQUEST, get_request_id


def _request_id() -> str | None:
    current = get_request_id()
    return None if current == NO_REQUEST else current


def api_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    response = drf_exception_handler(exc, context)
    if response is None:
        return None  # not an API error: Django's 500 handler answers in the same envelope
    details: Any = None
    if isinstance(exc, ValidationError):
        code, message, details = "validation_error", "The request was not valid.", response.data
    else:
        code = code_for_status(response.status_code)
        own_code = getattr(exc, "default_code", None)
        if response.status_code not in STATUS_CODES and isinstance(own_code, str):
            code = own_code  # an error with a status of its own, such as 422 variant_unavailable
        if isinstance(exc, NotAuthenticated):
            code = "not_authenticated"
        details = getattr(exc, "details", None)
        data = response.data
        raw = data.get("detail") if isinstance(data, dict) else None
        message = str(plain(raw)) if raw else "The request could not be completed."
        if isinstance(exc, Throttled) and exc.wait is not None:
            details = {"retry_after_seconds": math.ceil(exc.wait)}
    response.data = build_error(code, message, details=details, request_id=_request_id())
    return response


def server_error(request: HttpRequest, *args: Any, **kwargs: Any) -> JsonResponse:
    body = build_error(
        "server_error", "Something went wrong on our side.", request_id=_request_id()
    )
    return JsonResponse(body, status=500)


def not_found(request: HttpRequest, *args: Any, **kwargs: Any) -> JsonResponse:
    body = build_error("not_found", "Not found.", request_id=_request_id())
    return JsonResponse(body, status=404)
