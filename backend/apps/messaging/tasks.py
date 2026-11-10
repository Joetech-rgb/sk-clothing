"""Celery tasks for the outbox. The logic is in services.py; these only call it."""

from celery import shared_task

from . import services


@shared_task
def send_outbox_message(message_id: int) -> str:
    return services.deliver(message_id)


@shared_task
def dispatch_due_messages() -> int:
    """Sweep: free stuck messages, then send everything that is due. Runs every minute."""
    services.release_stuck()
    ids = services.due_ids()
    for message_id in ids:
        send_outbox_message.delay(message_id)
    return len(ids)
