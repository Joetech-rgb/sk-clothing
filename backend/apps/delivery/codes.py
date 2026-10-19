"""The delivery code. Pure Python.

Six digits, stored only as an HMAC, five wrong attempts then locked (CLAUDE.md section 5). The
HMAC is keyed with a server secret and bound to the order, so a leaked table cannot be reversed by
trying a million codes without the key, and one order's hash is useless for another.

Never log the code, the submitted value, or the state's hash.
"""

import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass, replace

DIGITS = 6
MAX_ATTEMPTS = 5

OK = "ok"
WRONG = "wrong"
LOCKED = "locked"
MALFORMED = "malformed"

_SHAPE = re.compile(rf"[0-9]{{{DIGITS}}}")


@dataclass(frozen=True)
class CodeState:
    code_hash: str
    failed_attempts: int = 0
    locked: bool = False

    def __repr__(self) -> str:  # keep the hash out of logs
        return f"CodeState(failed_attempts={self.failed_attempts}, locked={self.locked})"


def generate_code() -> str:
    return f"{secrets.randbelow(10**DIGITS):0{DIGITS}d}"


def hash_code(code: str, *, order_id: int | str, key: bytes) -> str:
    message = f"{order_id}:{code}".encode()
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def issue_code(*, order_id: int | str, key: bytes) -> tuple[str, CodeState]:
    """A new code and the state to store. Show or send the code, store only the state."""
    code = generate_code()
    return code, CodeState(code_hash=hash_code(code, order_id=order_id, key=key))


def check_code(
    state: CodeState, submitted: str, *, order_id: int | str, key: bytes
) -> tuple[CodeState, str]:
    """Check a code a rider or staff member typed. Returns the new state and OK, WRONG, LOCKED
    or MALFORMED. Input that is not six digits is not a guess, so it does not use an attempt."""
    if state.locked:
        return state, LOCKED
    cleaned = "".join(submitted.split())
    if not _SHAPE.fullmatch(cleaned):
        return state, MALFORMED
    expected = hash_code(cleaned, order_id=order_id, key=key)
    if hmac.compare_digest(expected.encode(), state.code_hash.encode()):
        return state, OK
    failed = state.failed_attempts + 1
    return replace(state, failed_attempts=failed, locked=failed >= MAX_ATTEMPTS), WRONG
