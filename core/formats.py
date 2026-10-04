"""Image format registry: supported formats, their capabilities and Pillow plugin setup."""
from __future__ import annotations

import contextlib
import enum
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, features

# "No limits": never reject huge images as decompression bombs.
Image.MAX_IMAGE_PIXELS = None

HEIF_AVAILABLE = False
try:  # HEIC/HEIF input
    import pillow_heif

    pillow_heif.register_heif_opener()
    HEIF_AVAILABLE = True
except Exception:  # pragma: no cover - depends on the environment
    pass

if not features.check("avif"):  # pragma: no cover - old Pillow builds
    with contextlib.suppress(Exception):
        import pillow_avif  # noqa: F401


class ImageFormat(enum.Enum):
    """Image formats known to ImgForge."""

    PNG = "PNG"
    JPEG = "JPEG"
    WEBP = "WEBP"
    AVIF = "AVIF"
    GIF = "GIF"
    BMP = "BMP"
    TIFF = "TIFF"
    HEIC = "HEIC"


@dataclass(frozen=True)
class FormatInfo:
    """Static capabilities of an image format."""

    label: str
    extension: str  # canonical extension used for output files
    extensions: tuple[str, ...]  # every extension accepted on input
    alpha: bool
    animation: bool
    icc: bool
    exif: bool
    writable: bool = True


_INFO: dict[ImageFormat, FormatInfo] = {
    ImageFormat.PNG: FormatInfo("PNG", ".png", (".png",), True, True, True, True),
    ImageFormat.JPEG: FormatInfo(
        "JPEG", ".jpg", (".jpg", ".jpeg", ".jpe", ".jfif"), False, False, True, True
    ),
    ImageFormat.WEBP: FormatInfo("WebP", ".webp", (".webp",), True, True, True, True),
    ImageFormat.AVIF: FormatInfo("AVIF", ".avif", (".avif",), True, True, True, True),
    ImageFormat.GIF: FormatInfo("GIF", ".gif", (".gif",), True, True, False, False),
    ImageFormat.BMP: FormatInfo("BMP", ".bmp", (".bmp",), False, False, False, False),
    # TIFF stores EXIF in a different way; only the ICC profile and DPI are carried over.
    ImageFormat.TIFF: FormatInfo("TIFF", ".tiff", (".tif", ".tiff"), True, False, True, False),
    ImageFormat.HEIC: FormatInfo(
        "HEIC", ".heic", (".heic", ".heif"), True, False, True, True, writable=False
    ),
}

OUTPUT_FORMATS: tuple[ImageFormat, ...] = tuple(f for f, i in _INFO.items() if i.writable)

_EXTENSION_MAP: dict[str, ImageFormat] = {
    ext: fmt for fmt, info in _INFO.items() for ext in info.extensions
}
INPUT_EXTENSIONS: frozenset[str] = frozenset(_EXTENSION_MAP)


def format_info(fmt: ImageFormat) -> FormatInfo:
    """Return the capability record for ``fmt``."""
    return _INFO[fmt]


def format_from_path(path: str | Path) -> ImageFormat | None:
    """Detect a supported input format from a file extension (``None`` if unsupported)."""
    return _EXTENSION_MAP.get(Path(path).suffix.lower())


def is_supported_input(path: str | Path) -> bool:
    """Whether ``path`` has an extension of a supported input format."""
    return format_from_path(path) is not None
