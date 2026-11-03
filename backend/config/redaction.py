"""Keep phone numbers out of logs (CLAUDE.md section 4). Pure Python.

Defence in depth: code should never log a number, but if one slips into a message it is masked
to its last three digits. The pattern can mask other numbers that look like phones; that is the
safe direction to be wrong in.
"""

import re

_PHONE = re.compile(r"(?<!\d)(?:\+?233|0)[\s-]?\d{2}[\s-]?\d{3}[\s-]?\d{4}(?!\d)")


def _mask(match: re.Match[str]) -> str:
    digits = re.sub(r"\D", "", match.group())
    return f"[phone ***{digits[-3:]}]"


def redact(text: str) -> str:
    return _PHONE.sub(_mask, text)
