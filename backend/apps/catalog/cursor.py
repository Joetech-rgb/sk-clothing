"""Opaque paging cursors. Pure Python.

The cursor carries an offset, so a caller cannot ask for an arbitrary expensive page, and a
tampered or hand-made cursor is refused instead of reaching the database.
"""

import base64
import binascii
import re

MAX_OFFSET = 10_000
_SHAPE = re.compile(r"o:([0-9]{1,7})")


def encode_cursor(offset: int) -> str:
    if not 0 <= offset <= MAX_OFFSET:
        raise ValueError("offset out of range")
    return base64.urlsafe_b64encode(f"o:{offset}".encode()).decode().rstrip("=")


def decode_cursor(value: str | None) -> int:
    """The offset a cursor stands for. No cursor means the first page. Raises ValueError."""
    if not value:
        return 0
    try:
        raw = base64.urlsafe_b64decode((value + "=" * (-len(value) % 4)).encode()).decode()
    except (binascii.Error, UnicodeDecodeError, ValueError) as error:
        raise ValueError("invalid cursor") from error
    match = _SHAPE.fullmatch(raw)
    if match is None or int(match.group(1)) > MAX_OFFSET:
        raise ValueError("invalid cursor")
    return int(match.group(1))
