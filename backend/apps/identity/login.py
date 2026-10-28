"""Phone login with a one-time code. The rules that must survive concurrent requests live here.

Guarantees, and what enforces each:
- At most five wrong guesses per code: the code's row is locked while it is checked, so
  simultaneous guesses are counted one at a time.
- A code works once: the same lock, and the live-code filter ignores consumed rows.
- One code per number per minute, and one live code at a time: requests for a number take turns
  (a PostgreSQL advisory lock), with a partial unique constraint as the backstop.
- The daily SMS cap cannot be exceeded: a single `UPDATE ... WHERE count < cap`, which the
  database applies to one request at a time.
- A customer account exists only after a correct code, and one number is one account: the unique
  constraint on the normalised phone, with a retry if two requests create it at the same moment.

Never log a code, a submitted value, a hash or a full number. Use mask_phone().
"""

import hashlib
import hmac
import logging
import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, transaction
from django.db.models import F
from django.utils import timezone

from apps.messaging.factory import ProviderNotConfigured, get_sms_provider

from . import otp
from .models import LoginCode, SmsDailyCount
from .phone import mask_phone, normalise_ghana_phone

logger = logging.getLogger(__name__)

DEFAULT_LIMITS: dict[str, int | str] = {
    "resend_gap_seconds": 60,  # one code per number per minute
    "codes_per_hour": 5,  # and five per number per hour
    "daily_sms_cap": 500,  # login SMS for the whole site, per day
    "request_ip_rate": "30/hour",  # requests for a code, per caller address
    "verify_ip_rate": "60/hour",  # attempts to verify, per caller address
}

INVALID = "invalid"
LOCKED = "locked"
OK = "ok"


def limit(name: str) -> int | str:
    """A limit, from the LOGIN_CODE_LIMITS setting if present, else the default."""
    return getattr(settings, "LOGIN_CODE_LIMITS", {}).get(name, DEFAULT_LIMITS[name])


class TooSoon(Exception):
    def __init__(self, wait_seconds: int) -> None:
        super().__init__("a code was requested too recently")
        self.wait_seconds = max(1, wait_seconds)


class DailyCapReached(Exception):
    pass


class SmsUnavailable(Exception):
    pass


@dataclass(frozen=True)
class VerifyResult:
    status: str  # OK, INVALID or LOCKED
    user_id: int | None = None
    is_new_customer: bool = False


def _now() -> datetime:
    return timezone.now()


def _key() -> bytes:
    return hmac.new(settings.SECRET_KEY.encode(), b"login-code-v1", hashlib.sha256).digest()


def _may_use_phone_login(phone: str) -> bool:
    """Staff and switched-off accounts never log in with a code (staff use password and 2FA)."""
    row = (
        get_user_model()
        .objects.filter(phone=phone)
        .values_list("is_staff", "is_superuser", "is_active")
        .first()
    )
    if row is None:
        return True
    is_staff, is_superuser, is_active = row
    return is_active and not is_staff and not is_superuser


def _lock_phone(phone: str) -> None:
    """Make requests for one number take turns, until the transaction ends. Without this, two
    simultaneous requests can both pass the one-a-minute check before either has committed, and
    the second then retires the first code and both are sent. Other numbers are not delayed."""
    if connection.vendor != "postgresql":
        return
    key = int.from_bytes(hashlib.sha256(phone.encode()).digest()[:8], "big", signed=True)
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [key])


def _enforce_phone_limits(phone: str, now: datetime) -> None:
    gap = timedelta(seconds=int(limit("resend_gap_seconds")))
    latest = (
        LoginCode.objects.filter(phone=phone, created_at__gt=now - gap)
        .order_by("-created_at")
        .first()
    )
    if latest is not None:
        raise TooSoon(math.ceil((latest.created_at + gap - now).total_seconds()))
    per_hour = int(limit("codes_per_hour"))
    window = timedelta(hours=1)
    stamps = list(
        LoginCode.objects.filter(phone=phone, created_at__gt=now - window)
        .order_by("created_at")
        .values_list("created_at", flat=True)
    )
    if len(stamps) >= per_hour:
        free_at = stamps[len(stamps) - per_hour] + window
        raise TooSoon(math.ceil((free_at - now).total_seconds()))


def _reserve_sms(now: datetime) -> None:
    """Take one message from today's allowance, or raise. Never lets the count pass the cap."""
    day = now.astimezone(UTC).date()
    SmsDailyCount.objects.get_or_create(day=day)
    taken = SmsDailyCount.objects.filter(day=day, count__lt=int(limit("daily_sms_cap"))).update(
        count=F("count") + 1
    )
    if not taken:
        raise DailyCapReached


def request_code(raw_phone: str, *, now: datetime | None = None) -> bool:
    """Issue and send a login code. Returns False if none was sent because this number may not
    use phone login (the caller still answers as if it had, so accounts cannot be probed).

    Raises InvalidPhone, TooSoon, DailyCapReached or SmsUnavailable.
    """
    now = now or _now()
    phone = normalise_ghana_phone(raw_phone)
    if not _may_use_phone_login(phone):
        return False
    try:
        provider = get_sms_provider()
    except ProviderNotConfigured as error:
        logger.error("login codes cannot be sent: no SMS provider is configured")
        raise SmsUnavailable from error
    code, record = otp.issue_otp(phone, now=now, key=_key())
    try:
        with transaction.atomic():
            _lock_phone(phone)
            _enforce_phone_limits(phone, now)
            LoginCode.objects.filter(phone=phone, consumed=False, superseded=False).update(
                superseded=True
            )
            try:
                with transaction.atomic():
                    row = LoginCode.objects.create(
                        phone=phone,
                        code_hash=record.code_hash,
                        expires_at=record.expires_at,
                        created_at=now,
                    )
            except IntegrityError as error:  # another request issued a live code a moment ago
                raise TooSoon(int(limit("resend_gap_seconds"))) from error
            _reserve_sms(now)  # last, so a refused request never uses up the allowance
    except (TooSoon, DailyCapReached):
        raise
    text = f"Your S.K Clothing code is {code}. It expires in 5 minutes."
    result = provider.send(phone, text, idempotency_key=f"login-code-{row.pk}")
    if not result.accepted:
        logger.warning("login code SMS was not accepted for %s", mask_phone(phone))
        raise SmsUnavailable
    logger.info("login code sent to %s", mask_phone(phone))
    return True


def _customer(phone: str) -> tuple["object | None", bool]:
    """The customer for this number, creating one if needed. None if the account is not allowed
    to use phone login. Safe if two requests create the same customer at once."""
    users = get_user_model().objects
    created = False
    user = users.filter(phone=phone).first()
    if user is None:
        try:
            with transaction.atomic():
                user = users.create_user(phone=phone)
                created = True
        except IntegrityError:  # someone else created it between our look and our insert
            user = users.get(phone=phone)
    if not user.is_active or user.is_staff or user.is_superuser:
        return None, False
    return user, created


def verify_code(raw_phone: str, submitted: str, *, now: datetime | None = None) -> VerifyResult:
    """Check a typed code. Counts wrong guesses and consumes a correct code atomically.

    The outcome is returned, not raised, on purpose: raising inside the transaction would roll
    back the wrong-guess count that must be kept.
    """
    now = now or _now()
    try:
        phone = normalise_ghana_phone(raw_phone)
    except ValueError:
        return VerifyResult(INVALID)
    with transaction.atomic():
        row = (
            LoginCode.objects.select_for_update()
            .filter(phone=phone, consumed=False, superseded=False)
            .first()
        )
        if row is None:
            return VerifyResult(INVALID)
        record = otp.OtpRecord(
            phone, row.code_hash, row.expires_at, row.failed_attempts, row.consumed
        )
        updated, status = otp.check_otp(record, submitted, now=now, key=_key())
        if status == otp.LOCKED:
            return VerifyResult(LOCKED)
        if status == otp.WRONG:
            row.failed_attempts = updated.failed_attempts
            row.save(update_fields=["failed_attempts"])
            return VerifyResult(INVALID)
        if status != otp.OK:  # expired, malformed (not counted) or already used
            return VerifyResult(INVALID)
        row.consumed = True
        row.save(update_fields=["consumed"])
        user, created = _customer(phone)
        if user is None:
            return VerifyResult(INVALID)
        return VerifyResult(OK, user.pk, created)
