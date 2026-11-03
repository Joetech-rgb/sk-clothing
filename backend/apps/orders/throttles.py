from config.throttling import AnonThrottle

from . import checkout


class CheckoutThrottle(AnonThrottle):
    """Checkouts per caller address. The rule that matters more, open unpaid orders per phone
    number, is enforced in the database transaction (checkout.py)."""

    scope = "checkout_ip"

    def get_rate(self) -> str:
        return str(checkout.limit("checkout_ip_rate"))


class LookupThrottle(AnonThrottle):
    """Order look-ups per caller address."""

    scope = "order_lookup_ip"

    def get_rate(self) -> str:
        return str(checkout.limit("lookup_ip_rate"))
