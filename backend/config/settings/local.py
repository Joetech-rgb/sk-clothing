from .base import *

DEBUG = True
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY") or "local-dev-only"

# Local development and CI have no Redis cache.
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
