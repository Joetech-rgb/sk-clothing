from .base import *

DEBUG = True
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY") or "local-dev-only"
