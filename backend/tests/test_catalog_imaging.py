import uuid
from io import BytesIO

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from PIL import Image, ImageCms

from apps.catalog.imaging import ImageRejected, process_image
from apps.catalog.media_keys import public_url, srcset, upload_key, variant_key


def make_image(fmt="JPEG", size=(800, 600), mode="RGB", **save_kwargs):
    buffer = BytesIO()
    Image.new(mode, size, "red" if mode != "1" else 1).save(buffer, fmt, **save_kwargs)
    return buffer.getvalue()


def widths(result):
    return [v.width for v in result.variants]


def rejected_code(raw, **kwargs):
    with pytest.raises(ImageRejected) as caught:
        process_image(raw, **kwargs)
    return caught.value.code


# --- sizes -----------------------------------------------------------------------


def test_large_photo_gets_every_size_and_is_webp():
    result = process_image(make_image(size=(4000, 3000)))
    assert widths(result) == [320, 640, 1024, 1600]
    assert [v.height for v in result.variants] == [240, 480, 768, 1200]
    for variant in result.variants:
        decoded = Image.open(BytesIO(variant.data))
        assert decoded.format == "WEBP"
        assert decoded.size == (variant.width, variant.height)
        assert variant.content_type == "image/webp"


def test_mid_size_photo_is_never_upscaled_and_keeps_its_own_width():
    assert widths(process_image(make_image(size=(1000, 500)))) == [320, 640, 1000]
    assert widths(process_image(make_image(size=(500, 400)))) == [320, 500]


def test_tiny_photo_gives_one_variant_at_its_own_size():
    result = process_image(make_image(size=(100, 80)))
    assert [(v.width, v.height) for v in result.variants] == [(100, 80)]


def test_exact_largest_width_is_included_once():
    assert widths(process_image(make_image(size=(1600, 900)))) == [320, 640, 1024, 1600]


def test_png_and_webp_inputs_are_accepted():
    assert process_image(make_image("PNG", (700, 700))).variants
    assert process_image(make_image("WEBP", (700, 700))).variants


# --- privacy and colour ----------------------------------------------------------


def test_exif_rotation_is_applied_and_exif_is_removed():
    exif = Image.Exif()
    exif[0x0112] = 6  # rotate: a 400x200 file is shown 200x400
    exif[0x010F] = "TestCam"
    exif.get_ifd(0x8825)[1] = "N"  # a GPS entry
    raw = make_image(size=(400, 200), exif=exif.tobytes())
    result = process_image(raw)
    assert (result.width, result.height) == (200, 400)
    for variant in result.variants:
        output = Image.open(BytesIO(variant.data))
        assert len(output.getexif()) == 0
        assert b"TestCam" not in variant.data


def test_real_transparency_is_kept():
    picture = Image.new("RGBA", (600, 600), (255, 0, 0, 255))
    picture.paste((0, 0, 255, 0), (0, 0, 300, 300))  # top-left quarter fully transparent
    buffer = BytesIO()
    picture.save(buffer, "PNG")
    output = Image.open(BytesIO(process_image(buffer.getvalue()).variants[0].data))
    output.load()
    assert output.mode == "RGBA"
    assert output.getpixel((10, 10))[3] == 0  # still see-through
    assert output.getpixel((output.width - 10, output.height - 10))[3] == 255  # still solid


def test_cmyk_jpeg_becomes_rgb():
    result = process_image(make_image("JPEG", (800, 600), mode="CMYK"))
    assert Image.open(BytesIO(result.variants[0].data)).mode == "RGB"


def test_embedded_srgb_profile_is_handled_and_not_copied_to_output():
    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    result = process_image(make_image(size=(800, 600), icc_profile=profile))
    output = Image.open(BytesIO(result.variants[0].data))
    assert output.info.get("icc_profile") is None


def test_unusable_colour_profile_falls_back_instead_of_failing():
    raw = make_image(size=(800, 600), icc_profile=b"this is not a profile")
    assert process_image(raw).variants


# --- hostile and broken input ----------------------------------------------------


def test_empty_garbage_and_text_are_rejected():
    assert rejected_code(b"") == "unreadable"
    assert rejected_code(b"not an image at all") == "unreadable"
    assert rejected_code(b"<?php echo 1; ?>") == "unreadable"


def test_file_over_the_byte_limit_is_rejected_before_decoding():
    assert rejected_code(make_image(size=(800, 600)), max_bytes=100) == "too_large"


def test_unsupported_formats_are_rejected():
    assert rejected_code(make_image("GIF", (100, 100), mode="P")) == "unsupported_format"
    assert rejected_code(make_image("BMP", (100, 100))) == "unsupported_format"


def test_truncated_file_is_rejected():
    raw = make_image(size=(1200, 900))
    assert rejected_code(raw[: len(raw) // 2]) == "unreadable"


def test_animated_image_is_rejected():
    buffer = BytesIO()
    frames = [Image.new("RGB", (100, 100), c) for c in ("red", "blue")]
    frames[0].save(buffer, "PNG", save_all=True, append_images=frames[1:])
    assert rejected_code(buffer.getvalue()) == "animated_not_supported"


def test_too_many_pixels_is_rejected_from_the_header():
    assert rejected_code(make_image(size=(200, 200)), max_pixels=1000) == "too_many_pixels"


def test_decompression_bomb_is_rejected_cheaply():
    # A bi-level PNG is tiny on disk but 196 million pixels once decoded.
    raw = make_image("PNG", (14000, 14000), mode="1")
    assert len(raw) < 1_000_000
    assert rejected_code(raw) == "too_many_pixels"


def test_extreme_side_length_is_rejected():
    raw = make_image("PNG", (20000, 4), mode="1")
    assert rejected_code(raw) == "too_many_pixels"


def test_empty_width_list_is_a_programming_error():
    with pytest.raises(ValueError):
        process_image(make_image(), widths=())


# --- property --------------------------------------------------------------------


@settings(max_examples=40, deadline=None)
@given(
    width=st.integers(min_value=1, max_value=900),
    height=st.integers(min_value=1, max_value=900),
)
def test_variants_never_upscale_and_keep_the_aspect_ratio(width, height):
    result = process_image(make_image("PNG", (width, height)))
    sizes = widths(result)
    assert sizes == sorted(set(sizes))
    assert sizes
    for variant in result.variants:
        assert 1 <= variant.width <= width
        assert variant.height >= 1
        assert abs(variant.height - height * variant.width / width) <= 1


# --- storage keys ----------------------------------------------------------------

IMAGE_ID = uuid.UUID("12345678-1234-5678-1234-567812345678")


def test_keys_use_only_ids_and_a_fixed_shape():
    assert upload_key(IMAGE_ID) == f"uploads/{IMAGE_ID}"
    assert variant_key(7, IMAGE_ID, 640) == f"media/products/7/{IMAGE_ID}/640.webp"


def test_public_url_has_exactly_one_slash():
    assert public_url("https://cdn.example.com/", "a/b") == "https://cdn.example.com/a/b"
    assert public_url("https://cdn.example.com", "a/b") == "https://cdn.example.com/a/b"


def test_srcset_is_smallest_first():
    value = srcset("https://cdn.example.com", 7, IMAGE_ID, [1024, 320])
    assert value == (
        f"https://cdn.example.com/media/products/7/{IMAGE_ID}/320.webp 320w, "
        f"https://cdn.example.com/media/products/7/{IMAGE_ID}/1024.webp 1024w"
    )
