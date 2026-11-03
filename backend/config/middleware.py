from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

from .request_ids import reset_request_id, resolve_request_id, set_request_id


class RequestIdMiddleware:
    """Give every request an ID, echo it in X-Request-ID, and tag Sentry with it."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request_id = resolve_request_id(request.headers.get("X-Request-ID"))
        request.request_id = request_id  # type: ignore[attr-defined]
        token = set_request_id(request_id)
        try:
            import sentry_sdk

            sentry_sdk.set_tag("request_id", request_id)
        except Exception:  # tagging must never break a request
            pass
        try:
            response = self.get_response(request)
        finally:
            reset_request_id(token)
        response["X-Request-ID"] = request_id
        return response
