"""The clean-up and refund jobs must actually be on the Celery beat schedule."""

from apps.identity.tasks import purge_old_login_codes
from apps.orders.tasks import cancel_stale_orders
from apps.payments.tasks import check_overdue_refunds, process_refunds
from config.settings import base


def scheduled():
    return {entry["task"]: entry["schedule"] for entry in base.CELERY_BEAT_SCHEDULE.values()}


def test_old_login_codes_are_cleared_once_a_day():
    assert scheduled()["apps.identity.tasks.purge_old_login_codes"] == 86400.0


def test_unpaid_orders_are_cancelled_every_hour():
    assert scheduled()["apps.orders.tasks.cancel_stale_orders"] == 3600.0


def test_refunds_are_processed_every_minute():
    assert scheduled()["apps.payments.tasks.process_refunds"] == 60.0


def test_overdue_refunds_raise_an_alarm_every_hour():
    assert scheduled()["apps.payments.tasks.check_overdue_refunds"] == 3600.0


def test_the_stock_expiry_schedule_is_still_there():
    assert scheduled()["apps.inventory.tasks.expire_reservations"] == 60.0


def test_the_scheduled_names_are_the_names_the_tasks_are_registered_under():
    assert purge_old_login_codes.name == "apps.identity.tasks.purge_old_login_codes"
    assert cancel_stale_orders.name == "apps.orders.tasks.cancel_stale_orders"
    assert process_refunds.name == "apps.payments.tasks.process_refunds"
    assert check_overdue_refunds.name == "apps.payments.tasks.check_overdue_refunds"
