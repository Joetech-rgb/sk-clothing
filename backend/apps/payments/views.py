import json
import logging

from django.conf import settings
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .client import PaystackError, ProviderNotConfigured, get_paystack_client
from .confirm import confirm_reference
from .parsing import parse_event
from .services import record_event
from .signature import verify_signature

logger = logging.getLogger(__name__)

CONFIRMING_EVENTS = frozenset({"charge.success"})


def _error(code: str, message: str, status: int) -> JsonResponse:
    return JsonResponse({"error": {"code": code, "message": message}}, status=status)


@csrf_exempt
@require_POST
def paystack_webhook(request: HttpRequest) -> JsonResponse:
    """Verify the signature, record the event once, and for a successful charge ask Paystack
    what really happened and apply it.

    Confirming runs for every delivery, including a repeat of an event we have already recorded:
    if the first attempt could not reach Paystack, it answered 503, Paystack sends the event
    again, and the repeat must still be allowed to finish the job. Confirming is safe to repeat.
    The body of the webhook is never trusted for the amount or the status.
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
    if event.event_type in CONFIRMING_EVENTS:
        try:
            confirm_reference(event.reference, client=get_paystack_client())
        except (PaystackError, ProviderNotConfigured):
            logger.error("paystack webhook could not confirm a payment: Paystack will retry")
            return _error("try_again", "Could not confirm the payment yet.", 503)
    return JsonResponse({"status": "received" if created else "duplicate"})
