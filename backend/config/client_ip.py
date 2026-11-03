"""Who is really calling. Pure Python.

Behind Cloudflare every request arrives from a Cloudflare address, so per-IP limits would treat
the whole country as one visitor. Cloudflare passes the real address in CF-Connecting-IP. That
header is only believable when the origin server accepts connections from Cloudflare alone, so it
is trusted only when TRUST_CLOUDFLARE_HEADERS is turned on (staging and production, once the
firewall rule is in place). Otherwise anyone could invent an address and dodge every limit.
"""

import ipaddress
from collections.abc import Mapping


def _valid(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return False
    return True


def client_ip(meta: Mapping[str, str], *, trust_cloudflare: bool) -> str:
    if trust_cloudflare:
        forwarded = meta.get("HTTP_CF_CONNECTING_IP", "").strip()
        if _valid(forwarded):
            return forwarded
    remote = meta.get("REMOTE_ADDR", "").strip()
    return remote if _valid(remote) else "unknown"
