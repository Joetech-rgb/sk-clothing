import logging
from collections.abc import Callable

import redis
from django.conf import settings
from django.db import connection
from django.http import HttpRequest, JsonResponse

logger = logging.getLogger(__name__)


def health(request: HttpRequest) -> JsonResponse:
    """Liveness: the process is up. Cheap, touches nothing."""
    return JsonResponse({"status": "ok"})


def _check_database() -> None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")


def _check_redis() -> None:
    client = redis.Redis.from_url(settings.CELERY_BROKER_URL, socket_connect_timeout=1)
    client.ping()


CHECKS: dict[str, Callable[[], None]] = {"database": _check_database, "redis": _check_redis}


def ready(request: HttpRequest) -> JsonResponse:
    """Readiness: can this server do real work? The uptime monitor should watch this one."""
    results = {}
    for name in settings.READINESS_CHECKS:
        try:
            CHECKS[name]()
            results[name] = "ok"
        except Exception:
            logger.warning("readiness check %s failed", name, exc_info=True)
            results[name] = "failed"
    healthy = all(value == "ok" for value in results.values())
    body = {"status": "ok" if healthy else "unavailable", "checks": results}
    return JsonResponse(body, status=200 if healthy else 503)
