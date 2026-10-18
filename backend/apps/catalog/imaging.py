"""Validate an uploaded photo and produce WebP sizes. Pure Python plus Pillow.

No Django, no network, no globals. Everything that touches storage lives elsewhere, so this
module can move to a shared home when returns and vendors need it, and can be swapped for a
libvips implementation without touching callers.

Safety rules, in the order they are applied:
1. Size in bytes is checked before anything is decoded.
2. The format is decided by decoding the header, never by file name or Content-Type.
3. Pixel count and side length are checked from the header, before pixels are decoded, so a
   tiny file that expands to gigabytes (a decompression bomb) is refused cheaply.
4. Animated images are refused.
5. EXIF is dropped (it can hold GPS location) after the rotation it asks for is applied.
6. Output is never larger than the source: small photos are not upscaled.
"""

import warnings
from collections.abc import Sequence
from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageCms, ImageOps, UnidentifiedImageError

DEFAULT_WIDTHS: tuple[int, ...] = (320, 640, 1024, 1600)
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
MAX_PIXELS = 50_000_000
MAX_SIDE = 10_000
WEBP_QUALITY = 80
ALLOWED_FORMATS = frozenset({"JPEG", "PNG", "WEBP"})


class ImageRejected(ValueError):
    """The upload cannot be used. `code` is stable, for the API and for tests."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ImageVariant:
    width: int
    height: int
    data: bytes
    content_type: str = "image/webp"


@dataclass(frozen=True)
class ProcessedImage:
    width: int  # after rotation, before resizing
    height: int
    variants: list[ImageVariant]  # ascending width


def _open(raw: bytes, max_pixels: int) -> Image.Image:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", Image.DecompressionBombWarning)
            image = Image.open(BytesIO(raw))
    except Image.DecompressionBombError as error:
        raise ImageRejected("too_many_pixels", "image has too many pixels") from error
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError) as error:
        raise ImageRejected("unreadable", "not a readable image") from error

    if image.format not in ALLOWED_FORMATS:
        raise ImageRejected("unsupported_format", "use a JPEG, PNG or WebP photo")
    if image.width * image.height > max_pixels or max(image.size) > MAX_SIDE:
        raise ImageRejected("too_many_pixels", "image is too large")
    if getattr(image, "is_animated", False):
        raise ImageRejected("animated_not_supported", "animated images are not supported")
    return image


def _to_srgb(image: Image.Image) -> Image.Image:
    """Convert from the embedded colour profile to sRGB so colours look the same on the web.

    Falls back to the image unchanged if the profile cannot be used.
    """
    profile = image.info.get("icc_profile")
    if not profile or image.mode not in ("RGB", "RGBA", "CMYK"):
        return image
    try:
        source = ImageCms.ImageCmsProfile(BytesIO(profile))
        target = ImageCms.createProfile("sRGB")
        output_mode = "RGBA" if image.mode == "RGBA" else "RGB"
        converted = ImageCms.profileToProfile(image, source, target, outputMode=output_mode)
    except (ImageCms.PyCMSError, OSError, ValueError):
        return image
    return converted if converted is not None else image


def _normalise(image: Image.Image) -> Image.Image:
    """Apply EXIF rotation, convert to sRGB, and leave a plain RGB or RGBA image."""
    rotated = ImageOps.exif_transpose(image)
    image = rotated if rotated is not None else image
    image = _to_srgb(image)
    if image.mode not in ("RGB", "RGBA"):
        has_alpha = image.mode in ("LA", "PA") or "transparency" in image.info
        image = image.convert("RGBA" if has_alpha else "RGB")
    image.info.clear()  # drops EXIF, GPS, and the colour profile we just applied
    return image


def _target_widths(source_width: int, widths: Sequence[int]) -> list[int]:
    targets = {w for w in widths if 0 < w <= source_width}
    if source_width < max(widths):
        targets.add(source_width)  # a small photo keeps its own size, never upscaled
    return sorted(targets)


def _encode(image: Image.Image, quality: int) -> bytes:
    buffer = BytesIO()
    try:
        image.save(buffer, "WEBP", quality=quality, method=4)
    except (ValueError, OSError) as error:
        raise ImageRejected("encode_failed", "could not encode the image") from error
    return buffer.getvalue()


def process_image(
    raw: bytes,
    widths: Sequence[int] = DEFAULT_WIDTHS,
    *,
    max_bytes: int = MAX_UPLOAD_BYTES,
    max_pixels: int = MAX_PIXELS,
    quality: int = WEBP_QUALITY,
) -> ProcessedImage:
    """Return WebP versions of the photo at each requested width, smallest first."""
    if not widths:
        raise ValueError("widths must not be empty")
    if not raw:
        raise ImageRejected("unreadable", "empty file")
    if len(raw) > max_bytes:
        raise ImageRejected("too_large", "file is too large")

    image = _open(raw, max_pixels)
    try:
        image.load()
    except (OSError, ValueError, SyntaxError) as error:
        raise ImageRejected("unreadable", "image is damaged or incomplete") from error

    try:
        image = _normalise(image)
    except (OSError, ValueError) as error:
        raise ImageRejected("unreadable", "image cannot be converted") from error

    variants = []
    for target in _target_widths(image.width, widths):
        if target == image.width:
            resized = image
        else:
            height = max(1, round(image.height * target / image.width))
            resized = image.resize(
                (target, height), Image.Resampling.LANCZOS, reducing_gap=2.0
            )
        variants.append(
            ImageVariant(
                width=resized.width,
                height=resized.height,
                data=_encode(resized, quality),
            )
        )
    return ProcessedImage(width=image.width, height=image.height, variants=variants)
