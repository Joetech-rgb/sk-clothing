import logging

from django.db import IntegrityError, transaction

from .models import PaystackWebhookEvent
from .parsing import ParsedEvent

logger = logging.getLogger(__name__)


def record_event(event: ParsedEvent) -> bool:
    """Store the event once. Returns True if new, False if it was already seen.

    Safe to call any number of times, including concurrently: the database unique
    constraint decides, not a read-then-write check.
    """
    try:
        with transaction.atomic():
            PaystackWebhookEvent.objects.create(
                dedupe_key=event.dedupe_key,
                event_type=event.event_type,
                reference=event.reference,
                amount=event.amount,
                currency=event.currency,
            )
    except IntegrityError:
        logger.info("paystack webhook duplicate event=%s", event.event_type)
        return False
    logger.info("paystack webhook recorded event=%s", event.event_type)
    return True
