import logging

from celery import shared_task

from . import refunds
from .client import ProviderNotConfigured, get_paystack_client

logger = logging.getLogger(__name__)


@shared_task
def process_refunds() -> dict[str, int]:
    """Create, send and follow up refunds. Runs every minute."""
    try:
        client = get_paystack_client()
    except ProviderNotConfigured:
        logger.error("refunds cannot be processed: Paystack is not configured")
        return {"queued": 0, "submitted": 0, "synced": 0, "stuck": 0}
    summary = refunds.process_refunds(client)
    return {
        "queued": summary.queued,
        "submitted": summary.submitted,
        "synced": summary.synced,
        "stuck": summary.stuck,
    }


@shared_task
def check_overdue_refunds() -> int:
    """Alarm for refunds still unresolved after 24 hours. Runs hourly."""
    return refunds.check_overdue_refunds()
