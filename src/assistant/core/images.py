"""Images as the model gets them: no larger than models look at, and small enough that several fit in a request.

Models scale an image down to about 1568 pixels on its long edge (Anthropic) or 2048 (OpenAI) anyway, so a
full-size screenshot costs megabytes of request for nothing, and some APIs refuse a request past a few megabytes
(GitHub Copilot answers 413). The file on disk stays as it was sent. Fitting is deterministic, so an earlier image
is sent the same on every call and the prompt cache keeps hitting.
"""

from io import BytesIO

from PIL import Image, ImageOps

MAX_EDGE = 1568
MAX_BYTES = 500_000
_JPEG_QUALITY = 85


def fit(data: bytes, media_type: str) -> tuple[bytes, str]:
    """The image and its media type, scaled down to `MAX_EDGE` and, when still over `MAX_BYTES`, as a JPEG.
    One within both, or one Pillow can't read (an SVG, a broken file), is returned as it is."""
    try:
        return _fitted(data, media_type)
    except (OSError, ValueError, Image.DecompressionBombError):
        return data, media_type


def _fitted(data: bytes, media_type: str) -> tuple[bytes, str]:
    image = Image.open(BytesIO(data))
    if max(image.size) <= MAX_EDGE and len(data) <= MAX_BYTES:
        return data, media_type
    was_jpeg = image.format == "JPEG"
    # A photo's orientation is in its EXIF data, which the encoded copy doesn't keep.
    image = ImageOps.exif_transpose(image)
    image.thumbnail((MAX_EDGE, MAX_EDGE))
    if not was_jpeg and len(png := _encoded(image, "PNG")) <= MAX_BYTES:
        return png, "image/png"
    return _encoded(_opaque(image), "JPEG", quality=_JPEG_QUALITY), "image/jpeg"


def _encoded(image: Image.Image, format: str, **options: int) -> bytes:
    out = BytesIO()
    image.save(out, format, **options)
    return out.getvalue()


def _opaque(image: Image.Image) -> Image.Image:
    """JPEG has no transparency: transparent parts become white, as an image viewer shows them."""
    if image.mode not in ("RGBA", "LA", "PA") and "transparency" not in image.info:
        return image.convert("RGB")
    rgba = image.convert("RGBA")
    white = Image.new("RGB", rgba.size, "white")
    white.paste(rgba, mask=rgba.getchannel("A"))
    return white
