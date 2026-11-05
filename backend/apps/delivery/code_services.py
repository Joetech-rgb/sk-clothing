"""Delivery code services. Other apps call these, never the delivery models directly.

The code is worked out from a stored nonce and a server secret (derived_codes.py), so it can be
shown to the customer again and sent by SMS, while the database holds nothing that reveals it.

Never log a code, a submitted value, a nonce or the key. Log order ids and actors only.
"""

import hashlib
import hmac
from dataclasses import dataclass
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .codes import LOCKED, MALFORMED, OK, WRONG
from .derived_codes import DerivedCodeState, check_derived, derive_code, new_nonce
from .models import DeliveryCode, DeliveryCodeEvent

__all__ = [
    "LOCKED",
    "MALFORMED",
    "NO_CODE",
    "OK",
    "PERMISSION",
    "WRONG",
    "CodeAlreadyUsed",
    "CodeNotIssued",
    "ShownCode",
    "can_confirm_delivery",
    "check_delivery_code",
    "code_for_display",
    "issue_delivery_code",
    "mark_code_used",
    "reissue_delivery_code",
]

NO_CODE = "no_code"
PERMISSION = "delivery.confirm_delivery"


class CodeNotIssued(Exception):
    pass


class CodeAlreadyUsed(Exception):
    pass


@dataclass(frozen=True)
class ShownCode:
    """What the order page may show: the code, unless it is locked or not issued yet."""

    code: str | None
    locked: bool


def _key() -> bytes:
    return hmac.new(settings.SECRET_KEY.encode(), b"delivery-code-v1", hashlib.sha256).digest()


def _record(order_id: int, kind: str, actor: str) -> None:
    DeliveryCodeEvent.objects.create(order_id=order_id, kind=kind, actor=actor)


def can_confirm_delivery(user: Any) -> bool:
    """Only an active account holding the confirm-delivery permission (riders, and staff given it
    through a group) may confirm a delivery. This is the one place that decides."""
    return bool(
        getattr(user, "is_authenticated", False)
        and getattr(user, "is_active", False)
        and user.has_perm(PERMISSION)
    )


def issue_delivery_code(order_id: int, *, actor: str) -> str:
    """Create the code for an order, once. Calling it again returns the same code.

    Returns the code so the caller can send it. Do not log it.
    """
    with transaction.atomic():
        row, created = DeliveryCode.objects.select_for_update().get_or_create(
            order_id=order_id, defaults={"nonce": new_nonce()}
        )
        if created:
            _record(order_id, "issued", actor)
        return derive_code(order_id=order_id, nonce=row.nonce, key=_key())


def code_for_display(order_id: int) -> ShownCode:
    """The code for the order page. A locked code is not shown: nobody can use it any more."""
    row = DeliveryCode.objects.filter(order_id=order_id).first()
    if row is None:
        return ShownCode(code=None, locked=False)
    if row.locked:
        return ShownCode(code=None, locked=True)
    return ShownCode(code=derive_code(order_id=order_id, nonce=row.nonce, key=_key()), locked=False)


def check_delivery_code(order_id: int, submitted: str, *, actor: str) -> str:
    """Check a code a rider or staff member typed. Returns OK, WRONG, LOCKED, MALFORMED or NO_CODE.

    The outcome is returned, not raised, on purpose: raising inside the caller's transaction would
    roll back the wrong-guess count, and the count is what stops guessing.
    """
    with transaction.atomic():
        row = DeliveryCode.objects.select_for_update().filter(order_id=order_id).first()
        if row is None:
            return NO_CODE
        state = DerivedCodeState(
            nonce=row.nonce, failed_attempts=row.failed_attempts, locked=row.locked
        )
        new_state, result = check_derived(state, submitted, order_id=order_id, key=_key())
        if result == WRONG:
            row.failed_attempts = new_state.failed_attempts
            row.locked = new_state.locked
            row.save(update_fields=["failed_attempts", "locked"])
            _record(order_id, "locked" if row.locked else "wrong", actor)
        return result


def mark_code_used(order_id: int, *, actor: str) -> None:
    """Record who entered the correct code, after the order has been marked delivered."""
    with transaction.atomic():
        row = DeliveryCode.objects.select_for_update().get(order_id=order_id)
        row.verified_at = timezone.now()
        row.confirmed_by = actor
        row.save(update_fields=["verified_at", "confirmed_by"])
        _record(order_id, "verified", actor)


def reissue_delivery_code(order_id: int, *, actor: str) -> str:
    """A fresh code for an order whose code is locked or lost. The caller must be staff.

    Raises CodeNotIssued if there is no code, and CodeAlreadyUsed if it was already confirmed.
    """
    with transaction.atomic():
        row = DeliveryCode.objects.select_for_update().filter(order_id=order_id).first()
        if row is None:
            raise CodeNotIssued
        if row.verified_at is not None:
            raise CodeAlreadyUsed
        row.nonce = new_nonce()
        row.failed_attempts = 0
        row.locked = False
        row.issue_number += 1
        row.issued_at = timezone.now()
        row.save(
            update_fields=["nonce", "failed_attempts", "locked", "issue_number", "issued_at"]
        )
        _record(order_id, "reissued", actor)
        return derive_code(order_id=order_id, nonce=row.nonce, key=_key())
