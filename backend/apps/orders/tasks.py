from celery import shared_task

from . import expiry


@shared_task
def cancel_stale_orders() -> int:
    """Cancel unpaid orders past their grace period and release their stock. Runs hourly."""
    return expiry.cancel_stale_orders()
