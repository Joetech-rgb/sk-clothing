import os

import sentry_sdk

from .base import *

sentry_sdk.init(dsn=os.environ.get("SENTRY_DSN", ""), environment="staging")
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
# The session cookie is sent only to this site, cannot be read by scripts, and is not sent on
# cross-site requests. The Origin check on the login endpoints is the second layer (ADR 0016).
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
# The storefront's own address (for example https://www.example.com), comma separated, set in
# the environment. Anything base.py already lists is kept.
CSRF_TRUSTED_ORIGINS = [
    *globals().get("CSRF_TRUSTED_ORIGINS", []),
    *[o.strip() for o in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()],
]
