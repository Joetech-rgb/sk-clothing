"""Login-CSRF defence for the two login endpoints.

These views set a session cookie, and API views are exempt from Django's CSRF middleware, so a
hostile web page could otherwise post a login form and sign a visitor in as the attacker. The
session cookie's SameSite setting helps but is not relied on alone. Three layers:

1. The API accepts JSON only, which a plain cross-site form cannot send.
2. The browser's Origin header, when present, must be this site or one of CSRF_TRUSTED_ORIGINS.
   "null" is refused.
3. Without an Origin header, a request the browser itself marks cross-site (Sec-Fetch-Site) is
   refused. Callers that send neither (the future apps, curl) are allowed through.

When the site sits behind a proxy, the storefront's own address must be listed in
CSRF_TRUSTED_ORIGINS, because Django may see the request as plain http.
"""

from django.conf import settings
from rest_framework.exceptions import APIException
from rest_framework.request import Request


class UntrustedOrigin(APIException):
    status_code = 403
    default_code = "bad_origin"
    default_detail = "This request did not come from our website."
    details = {"reason": "bad_origin"}


def check_origin(request: Request) -> None:
    origin = request.headers.get("Origin")
    if origin is not None:
        trusted = set(getattr(settings, "CSRF_TRUSTED_ORIGINS", []))
        trusted.add(f"{request.scheme}://{request.get_host()}")
        if origin not in trusted:
            raise UntrustedOrigin
        return
    if request.headers.get("Sec-Fetch-Site") == "cross-site":
        raise UntrustedOrigin
