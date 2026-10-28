"""Per-address limits for the login endpoints. These live in the cache and are a best-effort
brake on abuse from one address. The limits that must never fail (wrong guesses, single use, the
daily SMS cap) are in the database; see login.py."""

from config.throttling import AnonThrottle

from . import login


class _LoginIPThrottle(AnonThrottle):
    rate_name = ""

    def get_rate(self) -> str:
        return str(login.limit(self.rate_name))


class RequestCodeIPThrottle(_LoginIPThrottle):
    scope = "login_request_ip"
    rate_name = "request_ip_rate"


class VerifyCodeIPThrottle(_LoginIPThrottle):
    scope = "login_verify_ip"
    rate_name = "verify_ip_rate"
