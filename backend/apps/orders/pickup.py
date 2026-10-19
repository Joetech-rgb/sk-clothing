"""Pickup timing (CLAUDE.md section 5). Pure Python.

Pickup orders are held 7 days from the moment they are ready. A reminder goes out on day 3. After
day 7 the order is flagged uncollected and an admin chooses to leave it or refund it.
"""

from datetime import datetime, timedelta

REMINDER_AFTER = timedelta(days=3)
HOLD_FOR = timedelta(days=7)


def _aware(moment: datetime) -> None:
    if moment.tzinfo is None:
        raise ValueError("times must include a time zone")


def reminder_due_at(ready_at: datetime) -> datetime:
    _aware(ready_at)
    return ready_at + REMINDER_AFTER


def uncollected_after(ready_at: datetime) -> datetime:
    _aware(ready_at)
    return ready_at + HOLD_FOR


def reminder_due(ready_at: datetime, now: datetime) -> bool:
    """True once day 3 has been reached, until the hold ends. The caller sends it only once."""
    _aware(now)
    return reminder_due_at(ready_at) <= now < uncollected_after(ready_at)


def is_uncollected(ready_at: datetime, now: datetime) -> bool:
    _aware(now)
    return now >= uncollected_after(ready_at)
