import os

import sentry_sdk

from .base import *

sentry_sdk.init(dsn=os.environ.get("SENTRY_DSN", ""), environment="prod")
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
