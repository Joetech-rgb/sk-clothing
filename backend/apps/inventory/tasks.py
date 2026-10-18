from celery import shared_task

from .services import expire_overdue


@shared_task(name="apps.inventory.tasks.expire_reservations")
def expire_reservations() -> int:
    """Release holds older than 15 minutes. Returns how many were released."""
    return expire_overdue()
