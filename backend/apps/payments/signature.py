"""Paystack webhook signature check. Pure Python, no Django imports."""

import hashlib
import hmac


def compute_signature(raw_body: bytes, secret: str) -> str:
    """HMAC-SHA512 of the raw request body, hex encoded, as Paystack sends it."""
    return hmac.new(secret.encode(), raw_body, hashlib.sha512).hexdigest()


def verify_signature(raw_body: bytes, signature: str, secret: str) -> bool:
    """True only if the signature matches. Fails closed on a missing secret or signature."""
    if not secret or not signature:
        return False
    expected = compute_signature(raw_body, secret)
    return hmac.compare_digest(expected.encode(), signature.encode())
