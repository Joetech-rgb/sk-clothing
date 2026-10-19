"""One-time login codes. Pure Python.

Six digits, stored only as an HMAC, valid for five minutes, single use (CLAUDE.md section 4).
The brief does not give a limit on wrong guesses; five per code is a security default added here
(ADR 0010). Throttling per number and per IP and the daily SMS spend cap belong to the request
layer, where the rate-limit counters live.

Never log the code, the submitted value, or the stored hash.
"""

import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

DIGITS = 6
TTL = timedelta(minutes=5)
MAX_FAILED_ATTEMPTS = 5

OK = "ok"
WRONG = "wrong"
EXPIRED = "expired"
LOCKED = "locked"
USED = "used"
MALFORMED = "malformed"

_SHAPE = re.compile(rf"[0-9]{{{DIGITS}}}")


@dataclass(frozen=True)
class OtpRecord:
    phone: str  # E.164
    code_hash: str
    expires_at: datetime
    failed_attempts: int = 0
    consumed: bool = False

    def __repr__(self) -> str:  # keep the hash and number out of logs
        return f"OtpRecord(expires_at={self.expires_at}, failed_attempts={self.failed_attempts})"


def hash_code(phone: str, code: str, key: bytes) -> str:
    return hmac.new(key, f"{phone}:{code}".encode(), hashlib.sha256).hexdigest()


def issue_otp(phone: str, *, now: datetime, key: bytes) -> tuple[str, OtpRecord]:
    """A new code to send, and the record to store. `now` must carry a time zone."""
    if now.tzinfo is None:
        raise ValueError("now must include a time zone")
    code = f"{secrets.randbelow(10**DIGITS):0{DIGITS}d}"
    return code, OtpRecord(phone, hash_code(phone, code, key), now + TTL)


def check_otp(
    record: OtpRecord, submitted: str, *, now: datetime, key: bytes
) -> tuple[OtpRecord, str]:
    """Check a typed code. Returns the new record and OK, WRONG, EXPIRED, LOCKED, USED or
    MALFORMED. A correct code is accepted once; a code is valid while now < expires_at."""
    if now.tzinfo is None:
        raise ValueError("now must include a time zone")
    if record.consumed:
        return record, USED
    if now >= record.expires_at:
        return record, EXPIRED
    if record.failed_attempts >= MAX_FAILED_ATTEMPTS:
        return record, LOCKED
    cleaned = "".join(submitted.split())
    if not _SHAPE.fullmatch(cleaned):
        return record, MALFORMED
    expected = hash_code(record.phone, cleaned, key)
    if hmac.compare_digest(expected.encode(), record.code_hash.encode()):
        return replace(record, consumed=True), OK
    return replace(record, failed_attempts=record.failed_attempts + 1), WRONG
