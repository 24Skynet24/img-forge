"""Colour management and pixel-mode normalisation (ICC profiles, CMYK, 16-bit, palettes)."""
from __future__ import annotations

import io

from PIL import Image, ImageCms

RGB_MODES = ("RGB", "RGBA")
GRAY_MODES = ("L", "LA")
_SRGB: ImageCms.ImageCmsProfile | None = None


def _srgb_profile() -> ImageCms.ImageCmsProfile:
    global _SRGB
    if _SRGB is None:
        _SRGB = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB"))
    return _SRGB


def _open_profile(icc: bytes | None) -> ImageCms.ImageCmsProfile | None:
    if not icc:
        return None
    try:
        return ImageCms.ImageCmsProfile(io.BytesIO(icc))
    except Exception:
        return None


def _colorspace(profile: ImageCms.ImageCmsProfile) -> str:
    try:
        return str(profile.profile.xcolor_space).strip().upper()
    except Exception:
        return ""


def _is_srgb(profile: ImageCms.ImageCmsProfile) -> bool:
    try:
        return "srgb" in ImageCms.getProfileDescription(profile).lower()
    except Exception:
        return False


class SrgbTransform:
    """Converts RGB(A) images from a source ICC profile to sRGB."""

    def __init__(self, source: ImageCms.ImageCmsProfile) -> None:
        self._transform = ImageCms.buildTransform(source, _srgb_profile(), "RGB", "RGB")

    def __call__(self, img: Image.Image) -> Image.Image:
        if img.mode == "RGBA":
            out = ImageCms.applyTransform(img.convert("RGB"), self._transform)
            out.putalpha(img.getchannel("A"))
            return out
        return ImageCms.applyTransform(img, self._transform)


def to_srgb(img: Image.Image, icc: bytes | None) -> Image.Image:
    """Convert an RGB(A) image with an embedded ICC profile to sRGB (no-op otherwise)."""
    profile = _open_profile(icc)
    if profile is None or img.mode not in RGB_MODES or _colorspace(profile) != "RGB":
        return img
    if _is_srgb(profile):
        return img
    try:
        return SrgbTransform(profile)(img)
    except Exception:
        return img


def _cmyk_to_rgb(img: Image.Image, icc: bytes | None) -> Image.Image:
    profile = _open_profile(icc)
    if profile is not None and _colorspace(profile) == "CMYK":
        try:
            transform = ImageCms.buildTransform(profile, _srgb_profile(), "CMYK", "RGB")
            return ImageCms.applyTransform(img, transform)
        except Exception:
            pass
    return img.convert("RGB")



def to_working_mode(img: Image.Image, icc: bytes | None) -> Image.Image:
    """Normalise any Pillow mode to 8-bit L, LA, RGB or RGBA."""
    mode = img.mode
    if mode in ("L", "RGB") and "transparency" in img.info:  # colour-key transparency
        return img.convert("LA" if mode == "L" else "RGBA")
    if mode in ("RGB", "RGBA", "L", "LA"):
        return img
    if mode == "P":
        return img.convert("RGBA" if "transparency" in img.info else "RGB")
    if mode == "PA":
        return img.convert("RGBA")
    if mode == "1":
        return img.convert("L")
    if mode == "CMYK":
        return _cmyk_to_rgb(img, icc)
    if mode.startswith("I;16") or mode == "I":
        return img.point(lambda v: v * (1 / 256)).convert("L")
    if mode == "F":
        return img.convert("L")
    if mode == "La":
        return img.convert("LA")
    if mode == "RGBa":
        return img.convert("RGBA")
    return img.convert("RGB")  # YCbCr, LAB, HSV, RGBX, ...


def plan_icc(
    icc: bytes | None, mode: str, *, keep: bool, supported: bool
) -> tuple[ImageCms.ImageCmsProfile | None, bytes | None, str]:
    """Decide what to do with an ICC profile.

    Returns ``(profile_to_convert_from, icc_to_embed, colorspace)``. When the
    profile is not embedded, pixels of non-sRGB RGB images are converted to
    sRGB so the colours stay the same without a profile.
    """
    profile = _open_profile(icc)
    if profile is None:
        return None, None, ""
    space = _colorspace(profile)
    embed = icc if keep and supported else None
    if space == "RGB" and mode in RGB_MODES:
        if embed is not None or _is_srgb(profile):
            return None, embed, space
        return profile, None, space
    if space == "GRAY" and mode in GRAY_MODES:
        return None, embed, space
    return None, None, space  # mismatching or unsupported profile: drop it
