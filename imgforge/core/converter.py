"""Loading, normalising and encoding images (the "convert" half of the core).

``prepare_image`` turns any supported file into frames that are ready to be
written in a given target format (EXIF orientation applied, colour managed,
alpha flattened when needed). ``encode`` then writes those frames.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageCms, ImageSequence

from imgforge.core import compressor
from imgforge.core.formats import ImageFormat, format_info
from imgforge.core.options import ProcessingOptions, QualityLevel

EXIF_ORIENTATION = 0x0112
_ANIMATED_SOURCES = {"GIF", "WEBP", "PNG", "AVIF"}
_ORIENTATION_OPS = {
    2: Image.Transpose.FLIP_LEFT_RIGHT,
    3: Image.Transpose.ROTATE_180,
    4: Image.Transpose.FLIP_TOP_BOTTOM,
    5: Image.Transpose.TRANSPOSE,
    6: Image.Transpose.ROTATE_270,
    7: Image.Transpose.TRANSVERSE,
    8: Image.Transpose.ROTATE_90,
}
_RGB_MODES = ("RGB", "RGBA")
_GRAY_MODES = ("L", "LA")
_SRGB: ImageCms.ImageCmsProfile | None = None


@dataclass
class Prepared:
    """Frames and metadata ready to be encoded."""

    frames: list[Image.Image]
    durations: list[int] = field(default_factory=list)
    loop: int = 0
    exif: bytes | None = None
    icc: bytes | None = None
    dpi: tuple[float, float] | None = None
    warnings: list[str] = field(default_factory=list)
    source_size: tuple[int, int] = (0, 0)  # after EXIF orientation
    orientation: int = 1
    had_icc: bool = False
    private_metadata: bool = False  # EXIF/XMP/text that "remove metadata" would strip
    keep_metadata: bool = False

    @property
    def animated(self) -> bool:
        return len(self.frames) > 1

    @property
    def has_alpha(self) -> bool:
        return self.frames[0].mode in ("RGBA", "LA")


# --------------------------------------------------------------------------- colour


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


class _SrgbTransform:
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
    if profile is None or img.mode not in _RGB_MODES or _colorspace(profile) != "RGB":
        return img
    if _is_srgb(profile):
        return img
    try:
        return _SrgbTransform(profile)(img)
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


# --------------------------------------------------------------------------- modes


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


def apply_orientation(img: Image.Image, orientation: int) -> Image.Image:
    """Rotate/flip ``img`` according to an EXIF orientation value."""
    op = _ORIENTATION_OPS.get(orientation)
    return img.transpose(op) if op is not None else img


def has_transparency(img: Image.Image) -> bool:
    """True when an RGBA/LA image has at least one non-opaque pixel."""
    if img.mode not in ("RGBA", "LA"):
        return False
    return img.getchannel("A").getextrema()[0] < 255


def flatten_alpha(img: Image.Image, background: tuple[int, int, int]) -> Image.Image:
    """Composite an image with alpha onto a solid background colour."""
    if img.mode == "LA":
        img = img.convert("RGBA")
    if img.mode != "RGBA":
        return img
    base = Image.new("RGBA", img.size, (*background, 255))
    return Image.alpha_composite(base, img).convert("RGB")


def _drop_alpha(img: Image.Image) -> Image.Image:
    if img.mode == "RGBA":
        return img.convert("RGB")
    if img.mode == "LA":
        return img.convert("L")
    return img


def _adapt_to_target(
    img: Image.Image, fmt: ImageFormat, background: tuple[int, int, int]
) -> Image.Image:
    if not format_info(fmt).alpha:
        img = flatten_alpha(img, background)
    if fmt in (ImageFormat.WEBP, ImageFormat.AVIF):
        if img.mode == "L":
            img = img.convert("RGB")
        elif img.mode == "LA":
            img = img.convert("RGBA")
    elif fmt is ImageFormat.TIFF and img.mode == "LA":
        img = img.convert("RGBA")
    return img


# --------------------------------------------------------------------------- metadata


def _read_exif(im: Image.Image) -> Image.Exif | None:
    try:
        exif = im.getexif()
    except Exception:
        return None
    if im.format == "TIFF":
        # TIFF "EXIF" is really the file's own structural tags: keep orientation only.
        trimmed = Image.Exif()
        if EXIF_ORIENTATION in exif:
            trimmed[EXIF_ORIENTATION] = exif[EXIF_ORIENTATION]
        return trimmed if len(trimmed) else None
    return exif if len(exif) else None


def _read_dpi(im: Image.Image) -> tuple[float, float] | None:
    dpi = im.info.get("dpi")
    try:
        x, y = float(dpi[0]), float(dpi[1])
    except (TypeError, ValueError, IndexError):
        return None
    return (x, y) if x > 0 and y > 0 else None


def _has_private_metadata(im: Image.Image, exif: Image.Exif | None) -> bool:
    if exif is not None and any(tag != EXIF_ORIENTATION for tag in exif.keys()):
        return True
    info = im.info
    if info.get("xmp") or info.get("XML:com.adobe.xmp") or info.get("comment"):
        return True
    return bool(im.format == "PNG" and getattr(im, "text", None))


def _plan_icc(
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
    if space == "RGB" and mode in _RGB_MODES:
        if embed is not None or _is_srgb(profile):
            return None, embed, space
        return profile, None, space
    if space == "GRAY" and mode in _GRAY_MODES:
        return None, embed, space
    return None, None, space  # mismatching or unsupported profile: drop it


# --------------------------------------------------------------------------- loading


def _read_frames(im: Image.Image, animated: bool) -> tuple[list[Image.Image], list[int]]:
    if not animated:
        im.load()
        return [im.copy()], []
    frames: list[Image.Image] = []
    durations: list[int] = []
    for frame in ImageSequence.Iterator(im):
        frames.append(frame.convert("RGBA"))  # loads the frame; some plugins set info only then
        durations.append(int(frame.info.get("duration", im.info.get("duration", 100)) or 0))
    return frames, durations


def prepare_image(path: Path, target: ImageFormat, options: ProcessingOptions) -> Prepared:
    """Decode ``path`` and prepare it for encoding as ``target``.

    Applies EXIF orientation, normalises exotic modes (CMYK, 16-bit, palette,
    ...), manages ICC profiles, flattens transparency when the target has no
    alpha channel and keeps animation when the target supports it.
    """
    info = format_info(target)
    keep = not options.remove_metadata
    with Image.open(path) as im:
        src_format = im.format
        exif = _read_exif(im)
        orientation = int(exif.get(EXIF_ORIENTATION, 1) or 1) if exif is not None else 1
        icc = im.info.get("icc_profile")
        dpi = _read_dpi(im)
        private = _has_private_metadata(im, exif)
        loop = int(im.info.get("loop", 0) or 0)
        source_animated = bool(getattr(im, "is_animated", False)) and src_format in _ANIMATED_SOURCES
        keep_animation = source_animated and info.animation
        warnings: list[str] = []
        if source_animated and not info.animation:
            warnings.append(
                f"{info.label} не поддерживает анимацию — сохранён только первый кадр"
            )
        elif src_format == "TIFF" and getattr(im, "n_frames", 1) > 1:
            warnings.append("Многостраничный TIFF — сохранена только первая страница")
        raw_frames, durations = _read_frames(im, keep_animation)
        source_mode = raw_frames[0].mode

    frames = [apply_orientation(to_working_mode(f, icc), orientation) for f in raw_frames]
    del raw_frames
    source_size = frames[0].size

    # Colour management.
    cmyk = source_mode == "CMYK"
    transform_from, embed_icc, space = (
        (None, None, "") if cmyk else _plan_icc(icc, frames[0].mode, keep=keep, supported=info.icc)
    )
    if transform_from is not None:
        try:
            transform = _SrgbTransform(transform_from)
            frames = [transform(f) for f in frames]
        except Exception:
            pass

    # Drop fully opaque alpha channels (smaller files, simpler encoding).
    if not any(has_transparency(f) for f in frames):
        frames = [_drop_alpha(f) for f in frames]

    frames = [_adapt_to_target(f, target, options.background) for f in frames]
    for frame in frames:
        frame.info.clear()  # encoders fall back to info[...]: metadata is passed explicitly
    if embed_icc is not None and space == "GRAY" and frames[0].mode not in _GRAY_MODES:
        embed_icc = None

    # EXIF is written back only when metadata is kept, with orientation reset.
    exif_bytes: bytes | None = None
    if keep and info.exif and exif is not None:
        try:
            if EXIF_ORIENTATION in exif:
                exif[EXIF_ORIENTATION] = 1
            exif_bytes = exif.tobytes()
        except Exception:
            exif_bytes = None

    return Prepared(
        frames=frames,
        durations=durations,
        loop=loop,
        exif=exif_bytes,
        icc=embed_icc,
        dpi=dpi if keep else None,
        warnings=warnings,
        source_size=source_size,
        orientation=orientation,
        had_icc=bool(icc),
        private_metadata=private,
        keep_metadata=keep,
    )


# --------------------------------------------------------------------------- encoding


def _metadata_kwargs(prepared: Prepared, fmt: ImageFormat) -> dict:
    kwargs: dict = {}
    if prepared.exif and format_info(fmt).exif:
        kwargs["exif"] = prepared.exif
    if prepared.icc and format_info(fmt).icc:
        kwargs["icc_profile"] = prepared.icc
    if prepared.dpi and fmt in (ImageFormat.JPEG, ImageFormat.PNG, ImageFormat.TIFF):
        kwargs["dpi"] = prepared.dpi
    return kwargs


def _avif_speed(pixels: int, compress: bool) -> int:
    """AVIF encoder speed (0 = slowest). Speeds 0-1 are slower *and* not smaller than 2."""
    if not compress:
        return 6
    if pixels > 16_000_000:
        return 5
    if pixels > 4_000_000:
        return 4
    return 2


def encode(
    prepared: Prepared,
    fmt: ImageFormat,
    *,
    compress: bool,
    level: QualityLevel = QualityLevel.BALANCED,
    threads: int = 1,
) -> bytes:
    """Encode ``prepared`` as ``fmt``.

    With ``compress=False`` high-quality settings are used (convert only); with
    ``compress=True`` the settings of the compression ``level`` apply and the
    result is additionally optimised (oxipng, libimagequant, mozjpeg).
    """
    profile = compressor.PROFILES[level]
    frames = prepared.frames
    first = frames[0]
    extra = _metadata_kwargs(prepared, fmt)
    animation = (
        {
            "save_all": True,
            "append_images": frames[1:],
            "duration": prepared.durations,
            "loop": prepared.loop,
        }
        if prepared.animated
        else {}
    )
    buf = io.BytesIO()

    if fmt is ImageFormat.JPEG:
        if compress:
            first.save(
                buf, "JPEG", quality=profile.jpeg_quality, optimize=True, progressive=True,
                subsampling="4:2:0", **extra,
            )
            return compressor.optimize_jpeg(buf.getvalue())
        first.save(
            buf, "JPEG", quality=compressor.CONVERT_JPEG_QUALITY, optimize=True,
            subsampling="4:4:4", **extra,
        )
        return buf.getvalue()

    if fmt is ImageFormat.PNG:
        if prepared.animated:
            first.save(buf, "PNG", optimize=compress, **animation, **extra)
            return buf.getvalue()
        if compress:
            return compressor.compress_png(first, profile, extra, prepared.keep_metadata)
        first.save(buf, "PNG", compress_level=6, **extra)
        return buf.getvalue()

    if fmt is ImageFormat.WEBP:
        quality = profile.webp_quality if compress else compressor.CONVERT_WEBP_QUALITY
        first.save(
            buf, "WEBP", quality=quality, method=6 if compress else 4,
            minimize_size=compress and prepared.animated, **animation, **extra,
        )
        return buf.getvalue()

    if fmt is ImageFormat.AVIF:
        quality = profile.avif_quality if compress else compressor.CONVERT_AVIF_QUALITY
        first.save(
            buf, "AVIF", quality=quality,
            speed=_avif_speed(first.width * first.height, compress),
            subsampling="4:2:0" if compress else "4:4:4", max_threads=threads,
            **animation, **extra,
        )
        return buf.getvalue()

    if fmt is ImageFormat.GIF:
        colors = profile.gif_colors if compress else 256
        palettes = [compressor.to_gif_palette(f, colors) for f in frames]
        transparent = any("transparency" in p.info for p in palettes)
        kwargs: dict = {"optimize": True}
        if prepared.animated:
            kwargs.update(animation)
            kwargs["append_images"] = palettes[1:]
            if transparent:
                kwargs["disposal"] = 2
        palettes[0].save(buf, "GIF", **kwargs)
        return buf.getvalue()

    if fmt is ImageFormat.BMP:
        first.save(buf, "BMP")
        return buf.getvalue()

    if fmt is ImageFormat.TIFF:
        first.save(
            buf, "TIFF", compression="tiff_adobe_deflate" if compress else "tiff_lzw", **extra
        )
        return buf.getvalue()

    raise ValueError(f"Формат {fmt.value} не поддерживается для записи")
