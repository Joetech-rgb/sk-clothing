"""Object-storage key names for product photos. Pure functions.

Keys are built only from numeric ids and server-made UUIDs, never from a file name the user
chose, so there is no path trickery and no personal data in a URL. Every upload gets a new
UUID, so a published photo's URL never changes content and can be cached forever.
"""

import uuid
from collections.abc import Sequence

UPLOAD_PREFIX = "uploads/"
PUBLIC_PREFIX = "media/products/"


def upload_key(image_id: uuid.UUID) -> str:
    """Where the browser puts the original. Private, and expired by a bucket lifecycle rule."""
    return f"{UPLOAD_PREFIX}{image_id}"


def variant_key(product_id: int, image_id: uuid.UUID, width: int) -> str:
    return f"{PUBLIC_PREFIX}{product_id}/{image_id}/{width}.webp"


def public_url(base_url: str, key: str) -> str:
    return f"{base_url.rstrip('/')}/{key}"


def srcset(base_url: str, product_id: int, image_id: uuid.UUID, widths: Sequence[int]) -> str:
    """Value for an <img srcset>, smallest first."""
    return ", ".join(
        f"{public_url(base_url, variant_key(product_id, image_id, w))} {w}w"
        for w in sorted(widths)
    )
