"""Loading, normalising and encoding images (the "convert" half of the core).

``prepare_image`` turns any supported file into frames that are ready to be
written in a given target format (EXIF orientation applied, colour managed,
alpha flattened when needed). ``encode`` then writes those frames.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageSequence

from core import compressor
from core.color import GRAY_MODES, SrgbTransform, plan_icc, to_working_mode
from core.formats import ImageFormat, format_info
from core.options import ProcessingOptions, QualityLevel

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
    if exif is not None and any(tag != EXIF_ORIENTATION for tag in exif):
        return True
    info = im.info
    if info.get("xmp") or info.get("XML:com.adobe.xmp") or info.get("comment"):
        return True
    return bool(im.format == "PNG" and getattr(im, "text", None))


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
        (None, None, "") if cmyk else plan_icc(icc, frames[0].mode, keep=keep, supported=info.icc)
    )
    if transform_from is not None:
        try:
            transform = SrgbTransform(transform_from)
            frames = [transform(f) for f in frames]
        except Exception:
            pass

    # Drop fully opaque alpha channels (smaller files, simpler encoding).
    if not any(has_transparency(f) for f in frames):
        frames = [_drop_alpha(f) for f in frames]

    frames = [_adapt_to_target(f, target, options.background) for f in frames]
    for frame in frames:
        frame.info.clear()  # encoders fall back to info[...]: metadata is passed explicitly
    if embed_icc is not None and space == "GRAY" and frames[0].mode not in GRAY_MODES:
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
