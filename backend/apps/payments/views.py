import json
import logging

from django.conf import settings
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .parsing import parse_event
from .services import record_event
from .signature import verify_signature

logger = logging.getLogger(__name__)


def _error(code: str, message: str, status: int) -> JsonResponse:
    return JsonResponse({"error": {"code": code, "message": message}}, status=status)


@csrf_exempt
@require_POST
def paystack_webhook(request: HttpRequest) -> JsonResponse:
    """Phase 0: verify the signature and record the event once. Nothing else.

    No order exists yet, so this never marks anything paid.
    """
    raw_body = request.body
    signature = request.headers.get("x-paystack-signature", "")
    if not verify_signature(raw_body, signature, settings.PAYSTACK_SECRET_KEY):
        return _error("invalid_signature", "Signature check failed.", 401)

    try:
        payload = json.loads(raw_body)
    except ValueError:
        return _error("invalid_json", "Body is not valid JSON.", 400)

    event = parse_event(payload)
    if event is None:
        logger.warning("paystack webhook ignored: unrecognised shape")
        return JsonResponse({"status": "ignored"})

    created = record_event(event)
    return JsonResponse({"status": "received" if created else "duplicate"})
