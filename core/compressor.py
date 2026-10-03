"""Compression presets and size-reduction primitives (libimagequant, oxipng, mozjpeg)."""
from __future__ import annotations

import io
from dataclasses import dataclass

import imagequant
import mozjpeg_lossless_optimization as mozjpeg
import oxipng
from PIL import Image

from core.options import QualityLevel

COPY_MARKERS = mozjpeg.COPY_MARKERS


@dataclass(frozen=True)
class Profile:
    """Encoder settings for one position of the compression-level slider."""

    jpeg_quality: int
    webp_quality: int
    avif_quality: int
    png_min_quality: int  # libimagequant: abort (and stay lossless) below this
    png_max_quality: int
    oxipng_level: int
    gif_colors: int


PROFILES: dict[QualityLevel, Profile] = {
    QualityLevel.MAXIMUM: Profile(90, 90, 88, 90, 100, 2, 256),
    QualityLevel.BALANCED: Profile(82, 80, 78, 65, 90, 3, 256),
    QualityLevel.SMALLEST: Profile(72, 68, 65, 40, 80, 4, 128),
}

# Settings used when only converting (no extra compression): high quality.
CONVERT_JPEG_QUALITY = 95
CONVERT_WEBP_QUALITY = 95
CONVERT_AVIF_QUALITY = 90


def quantize_rgba(
    img: Image.Image,
    *,
    colors: int = 256,
    min_quality: int = 0,
    max_quality: int = 100,
    dithering: float = 1.0,
) -> tuple[Image.Image, list[int]] | None:
    """Quantize ``img`` to a palette image with libimagequant.

    Returns ``(palette_image, alpha_per_palette_entry)`` or ``None`` when the
    requested minimum quality cannot be reached.
    """
    rgba = img.convert("RGBA")
    try:
        data, palette = imagequant.quantize_raw_rgba_bytes(
            rgba.tobytes(),
            rgba.width,
            rgba.height,
            dithering_level=dithering,
            max_colors=colors,
            min_quality=min_quality,
            max_quality=max_quality,
        )
    except RuntimeError:
        return None
    out = Image.frombytes("P", rgba.size, data)
    out.putpalette([c for i, c in enumerate(palette) if i % 4 != 3])
    return out, list(palette[3::4])


def _trim_alpha(alphas: list[int]) -> bytes | None:
    """tRNS payload: alpha values up to the last non-opaque palette entry."""
    last = -1
    for i, a in enumerate(alphas):
        if a < 255:
            last = i
    return bytes(alphas[: last + 1]) if last >= 0 else None


def oxipng_optimize(data: bytes, level: int, keep_metadata: bool) -> bytes:
    """Losslessly optimise PNG bytes with oxipng (returns the input on failure)."""
    strip = oxipng.StripChunks.none() if keep_metadata else oxipng.StripChunks.safe()
    try:
        out = oxipng.optimize_from_memory(data, level=level, strip=strip, optimize_alpha=True)
    except Exception:
        return data
    return out if len(out) < len(data) else data


def compress_png(
    img: Image.Image, profile: Profile, save_kwargs: dict, keep_metadata: bool
) -> bytes:
    """Palette-quantize (when quality allows) and oxipng-optimise a still image."""
    quantized = None
    if img.mode in ("RGB", "RGBA"):
        quantized = quantize_rgba(
            img,
            colors=256,
            min_quality=profile.png_min_quality,
            max_quality=profile.png_max_quality,
        )
    buf = io.BytesIO()
    if quantized is not None:
        palette_img, alphas = quantized
        kwargs = dict(save_kwargs)
        transparency = _trim_alpha(alphas)
        if transparency is not None:
            kwargs["transparency"] = transparency
        palette_img.save(buf, "PNG", optimize=True, **kwargs)
    else:
        img.save(buf, "PNG", optimize=True, **save_kwargs)
    return oxipng_optimize(buf.getvalue(), profile.oxipng_level, keep_metadata)


def optimize_jpeg(data: bytes, copy: int = COPY_MARKERS.ALL) -> bytes:
    """Losslessly re-encode JPEG bytes (progressive, optimised Huffman) with mozjpeg."""
    try:
        out = mozjpeg.optimize(data, copy=copy)
    except Exception:
        return data
    return out if len(out) < len(data) else data


def to_gif_palette(img: Image.Image, colors: int) -> Image.Image:
    """Convert ``img`` to a palette image suitable for GIF.

    GIF only has 1-bit transparency: pixels with alpha < 128 become the
    transparent index, which is stored in ``info["transparency"]``.
    """
    rgba = img.convert("RGBA")
    alpha = rgba.getchannel("A")
    has_transparency = alpha.getextrema()[0] < 128
    max_colors = min(colors, 255) if has_transparency else colors
    if has_transparency:
        rgba.putalpha(alpha.point(lambda a: 255 if a >= 128 else 0))
    quantized = quantize_rgba(rgba, colors=max_colors, dithering=1.0)
    assert quantized is not None  # min_quality=0 can always be met
    palette_img, alphas = quantized
    if not has_transparency:
        return palette_img
    transparent = [i for i, a in enumerate(alphas) if a < 128]
    if not transparent:
        return palette_img
    target = transparent[0]
    table = bytearray(range(256))
    for i in transparent:
        table[i] = target
    remapped = Image.frombytes("P", palette_img.size, palette_img.tobytes().translate(bytes(table)))
    remapped.putpalette(palette_img.getpalette() or [])
    remapped.info["transparency"] = target
    return remapped
