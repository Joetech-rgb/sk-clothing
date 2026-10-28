from celery import shared_task

from . import login


@shared_task
def purge_old_login_codes() -> int:
    """Delete login codes older than a week. Meant to run once a day."""
    return login.purge_old_login_codes()
