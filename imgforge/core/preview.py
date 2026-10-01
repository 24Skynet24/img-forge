"""Display-oriented image loading for thumbnails and the before/after view."""
from __future__ import annotations

from pathlib import Path

from PIL import Image

from imgforge.core.converter import (
    EXIF_ORIENTATION,
    to_working_mode,
    apply_orientation,
    to_srgb,
)


def _load_upright_rgba(path: Path, *, max_side: int | None, colour_managed: bool) -> Image.Image:
    with Image.open(path) as im:
        if max_side is not None:
            im.draft("RGB", (max_side * 2, max_side * 2))  # fast JPEG downscale on decode
        try:
            orientation = int(im.getexif().get(EXIF_ORIENTATION, 1) or 1)
        except Exception:
            orientation = 1
        icc = im.info.get("icc_profile")
        im.load()
        img = to_working_mode(im.copy(), icc)
    if max_side is not None:
        img.thumbnail((max_side * 2, max_side * 2), Image.Resampling.BILINEAR)
    img = apply_orientation(img, orientation)
    if colour_managed:
        img = to_srgb(img, icc)
    if max_side is not None:
        img.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    return img.convert("RGBA")


def load_thumbnail(path: Path, size: int = 96) -> Image.Image:
    """Small RGBA thumbnail (at most ``size`` px on the long side), orientation applied."""
    return _load_upright_rgba(path, max_side=size, colour_managed=False)


def load_display_image(path: Path) -> Image.Image:
    """Full-resolution RGBA image (first frame), orientation applied and converted to sRGB."""
    return _load_upright_rgba(path, max_side=None, colour_managed=True)
