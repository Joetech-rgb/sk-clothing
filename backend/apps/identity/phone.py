"""Ghana phone numbers. Pure Python.

Everything is stored as E.164 (+233 followed by nine digits) so the same person always matches.
Accepted spellings include 024 123 4567, 0241234567, 241234567, 233241234567, +233 24 123 4567
and 00233 24 123 4567. Numbers from other countries are refused (assumption, ADR 0010).

Never log a full number. Use mask_phone() in logs.
"""

import re

COUNTRY_CODE = "233"
_ALLOWED_PUNCTUATION = re.compile(r"[ \-().]")
_DIGITS = re.compile(r"[0-9]+")


class InvalidPhone(ValueError):
    pass


def normalise_ghana_phone(raw: str) -> str:
    if not isinstance(raw, str):
        raise InvalidPhone("phone must be text")
    text = _ALLOWED_PUNCTUATION.sub("", raw.strip())
    has_plus = text.startswith("+")
    digits = text[1:] if has_plus else text
    if not _DIGITS.fullmatch(digits):  # also rejects non-ASCII digits and letters
        raise InvalidPhone("phone has characters that are not allowed")

    if has_plus:
        if not digits.startswith(COUNTRY_CODE):
            raise InvalidPhone("only Ghana numbers are accepted")
        national = digits[len(COUNTRY_CODE) :]
    elif digits.startswith("00"):
        if not digits[2:].startswith(COUNTRY_CODE):
            raise InvalidPhone("only Ghana numbers are accepted")
        national = digits[2 + len(COUNTRY_CODE) :]
    elif digits.startswith(COUNTRY_CODE) and len(digits) == 12:
        national = digits[len(COUNTRY_CODE) :]
    elif digits.startswith("0") and len(digits) == 10:
        national = digits[1:]
    elif len(digits) == 9:
        national = digits
    else:
        raise InvalidPhone("phone is not a valid Ghana number")

    if len(national) != 9 or national.startswith("0"):
        raise InvalidPhone("phone is not a valid Ghana number")
    return f"+{COUNTRY_CODE}{national}"


def mask_phone(e164: str) -> str:
    """For logs: keeps the country code and the last three digits."""
    if len(e164) < 8:
        return "*" * len(e164)
    return e164[:4] + "*" * (len(e164) - 7) + e164[-3:]
