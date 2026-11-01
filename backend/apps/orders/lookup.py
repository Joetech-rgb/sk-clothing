"""Letting a customer look an order up again with the order reference and the phone number it was
placed with. Guests have no account, so the phone number is the proof.

A wrong reference and a wrong phone number give the same answer, so nobody can use this to find
out which references exist.
"""

import hmac

from apps.identity.phone import InvalidPhone, normalise_ghana_phone

from .models import Order


def find_order(reference: str, phone: str) -> Order | None:
    try:
        wanted = normalise_ghana_phone(phone)
    except InvalidPhone:
        return None
    order = Order.objects.filter(reference=reference.strip().upper()).first()
    if order is None or not order.contact_phone:
        return None
    if not hmac.compare_digest(order.contact_phone.encode(), wanted.encode()):
        return None
    return order
