"""The delivery code, derived instead of stored. Pure Python.

Why: the brief wants the code stored as an HMAC and also shown on the order page. A hash cannot be
shown again. So the code is derived on demand, the way one-time passwords are (RFC 4226): an HMAC
of the order id and a random nonce, keyed with a server secret, cut down to six digits. Only the
nonce and the attempt state are stored. Whoever reads the table cannot work out a code without the
key, and a code for one order is useless for another.

Same rules as before: six digits, five wrong attempts then locked, input that is not six digits is
not a guess. Never log the code, the submitted value, the nonce or the key.
"""

import hashlib
import hmac
import secrets
from dataclasses import dataclass, replace

from .codes import _SHAPE, DIGITS, LOCKED, MALFORMED, MAX_ATTEMPTS, OK, WRONG

_DOMAIN = b"sk-delivery-code-v1"


@dataclass(frozen=True)
class DerivedCodeState:
    nonce: str
    failed_attempts: int = 0
    locked: bool = False

    def __repr__(self) -> str:  # keep the nonce out of logs
        return f"DerivedCodeState(failed_attempts={self.failed_attempts}, locked={self.locked})"


def new_nonce() -> str:
    return secrets.token_hex(16)


def derive_code(*, order_id: int | str, nonce: str, key: bytes) -> str:
    """The six-digit code for this order and nonce (RFC 4226 dynamic truncation, SHA-256).

    Eight bytes are read at a data-dependent offset and reduced modulo 10**6; with 64 bits the
    bias from the reduction is far below anything measurable.
    """
    message = _DOMAIN + b":" + f"{order_id}:{nonce}".encode()
    mac = hmac.new(key, message, hashlib.sha256).digest()
    offset = mac[-1] & 0x0F
    value = int.from_bytes(mac[offset : offset + 8], "big")
    return f"{value % 10**DIGITS:0{DIGITS}d}"


def issue_derived(*, order_id: int | str, key: bytes) -> tuple[str, DerivedCodeState]:
    """A new nonce, the code it gives, and the state to store. Store the state, not the code."""
    nonce = new_nonce()
    return derive_code(order_id=order_id, nonce=nonce, key=key), DerivedCodeState(nonce=nonce)


def check_derived(
    state: DerivedCodeState, submitted: str, *, order_id: int | str, key: bytes
) -> tuple[DerivedCodeState, str]:
    """Check a typed code. Returns the new state and OK, WRONG, LOCKED or MALFORMED."""
    if state.locked:
        return state, LOCKED
    cleaned = "".join(submitted.split())
    if not _SHAPE.fullmatch(cleaned):
        return state, MALFORMED
    expected = derive_code(order_id=order_id, nonce=state.nonce, key=key)
    if hmac.compare_digest(expected.encode(), cleaned.encode()):
        return state, OK
    failed = state.failed_attempts + 1
    return replace(state, failed_attempts=failed, locked=failed >= MAX_ATTEMPTS), WRONG
