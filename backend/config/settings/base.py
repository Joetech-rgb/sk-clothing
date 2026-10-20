import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
DEBUG = False
ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "localhost").split(",")

# Register each app under backend/apps here only when its phase starts.
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
    "simple_history",
    "apps.identity",
    "apps.payments",
    "apps.catalog",
    "apps.inventory",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Chosen before any real database exists, because changing it later means rewriting live data.
AUTH_USER_MODEL = "identity.User"

MIDDLEWARE = [
    "config.middleware.RequestIdMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
TEMPLATES = [{"BACKEND": "django.template.backends.django.DjangoTemplates", "APP_DIRS": True, "OPTIONS": {"context_processors": ["django.template.context_processors.request", "django.contrib.auth.context_processors.auth", "django.contrib.messages.context_processors.messages"]}}]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "skclothing"),
        "USER": os.environ.get("POSTGRES_USER", "sk"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
        "HOST": os.environ.get("POSTGRES_HOST", "db"),
        "PORT": "5432",
    }
}

LANGUAGE_CODE = "en"
TIME_ZONE = "Africa/Accra"
USE_TZ = True
CURRENCY = "GHS"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

CELERY_BROKER_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")
CELERY_TIMEZONE = "Africa/Accra"
CELERY_BEAT_SCHEDULE = {
    # Stock held for a checkout is released after 15 minutes. Runs every minute.
    "expire-stock-reservations": {
        "task": "apps.inventory.tasks.expire_reservations",
        "schedule": 60.0,
    },
}

# The cache is a separate Redis from the Celery broker: the broker must never evict queued
# tasks, a cache must be free to (ADR 0009). Throttle counters live here, shared by all workers.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": os.environ.get("CACHE_URL", "redis://redis:6379/1"),
    }
}

# Believe CF-Connecting-IP only when the server accepts traffic from Cloudflare alone.
TRUST_CLOUDFLARE_HEADERS = os.environ.get("TRUST_CLOUDFLARE_HEADERS", "") == "1"

# What /api/v1/health/ready/ checks. Tests turn Redis off.
READINESS_CHECKS = ("database", "redis")

REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "config.api_errors.api_exception_handler",
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    # Sessions for the website. No Basic auth: it would send the password with every request.
    "DEFAULT_AUTHENTICATION_CLASSES": ["config.authentication.SessionAuthentication401"],
    # Secure by default: an endpoint is private unless it says otherwise.
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_THROTTLE_CLASSES": ["config.throttling.AnonThrottle", "config.throttling.UserThrottle"],
    # Generous on purpose: many phones share one carrier address. Login and payment endpoints
    # get tighter limits of their own.
    "DEFAULT_THROTTLE_RATES": {"anon": "300/min", "user": "600/min"},
}
SPECTACULAR_SETTINGS = {"TITLE": "S.K Clothing API", "VERSION": "1.0.0"}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "request_id": {"()": "config.logging_filters.RequestIdFilter"},
        "redact": {"()": "config.logging_filters.RedactingFilter"},
    },
    "formatters": {
        "plain": {"format": "%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s"}
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "filters": ["request_id", "redact"],
            "formatter": "plain",
        }
    },
    "root": {"handlers": ["console"], "level": os.environ.get("LOG_LEVEL", "INFO")},
}

# Paystack. Empty means every webhook is rejected (fails closed).
PAYSTACK_SECRET_KEY = os.environ.get("PAYSTACK_SECRET_KEY", "")
