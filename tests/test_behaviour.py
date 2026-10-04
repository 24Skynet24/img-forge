"""Animation, EXIF orientation, metadata, ICC and the "never bigger" fallback."""
from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image, ImageCms

from core.formats import ImageFormat
from core.models import Status
from core.options import Mode, QualityLevel

from .conftest import gradient_image, noise_image, run_one

DURATIONS = [60, 120, 180]


def make_animation(path: Path, fmt: str = "GIF", transparent: bool = False) -> Path:
    frames = []
    for i, colour in enumerate([(255, 0, 0), (0, 255, 0), (0, 0, 255)]):
        img = Image.new("RGBA" if transparent else "RGB", (40, 30), (*colour, 255) if transparent else colour)
        for x in range(10 * i, 10 * i + 10):  # a moving transparent hole / marker
            for y in range(30):
                img.putpixel((x, y), (0, 0, 0, 0) if transparent else (255, 255, 255))
        frames.append(img)
    kwargs = {"save_all": True, "append_images": frames[1:], "duration": DURATIONS, "loop": 0}
    if fmt == "GIF" and transparent:
        kwargs["disposal"] = 2
    frames[0].save(path, fmt, **kwargs)
    return path


def frame_info(path: Path) -> tuple[int, list[int]]:
    with Image.open(path) as im:
        n = getattr(im, "n_frames", 1)
        durations = []
        for i in range(n):
            im.seek(i)
            im.load()  # some plugins (WebP, AVIF) fill info["duration"] only on load
            durations.append(im.info.get("duration"))
    return n, durations


# ------------------------------------------------------------------ animation


@pytest.mark.parametrize("source", ["GIF", "WEBP"])
@pytest.mark.parametrize("target", [ImageFormat.GIF, ImageFormat.WEBP, ImageFormat.PNG, ImageFormat.AVIF])
def test_animation_keeps_frames_and_timings(tmp_path: Path, work_dir: Path, source, target) -> None:
    src = make_animation(tmp_path / f"anim.{source.lower()}", source)
    result = run_one(src, work_dir, mode=Mode.CONVERT, target_format=target)
    assert result.status is Status.OK, result.message
    assert not result.warnings
    n, durations = frame_info(result.output_path)
    assert n == 3
    # GIF stores centiseconds, codecs may round slightly.
    for got, expected in zip(durations, DURATIONS, strict=True):
        assert abs(got - expected) <= 20, (durations, DURATIONS)


def test_animated_gif_compress_only(tmp_path: Path, work_dir: Path) -> None:
    src = make_animation(tmp_path / "anim.gif")
    result = run_one(src, work_dir, mode=Mode.COMPRESS)
    assert result.status in (Status.OK, Status.ALREADY_OPTIMIZED)
    assert frame_info(result.output_path)[0] == 3


def test_animated_gif_transparency_survives(tmp_path: Path, work_dir: Path) -> None:
    src = make_animation(tmp_path / "hole.gif", transparent=True)
    result = run_one(src, work_dir, mode=Mode.CONVERT, target_format=ImageFormat.GIF)
    with Image.open(result.output_path) as im:
        assert im.n_frames == 3
        for i in range(3):
            im.seek(i)
            rgba = im.convert("RGBA")
            assert rgba.getpixel((10 * i + 5, 15))[3] == 0, f"frame {i}: hole should be transparent"
            assert rgba.getpixel((39 if i < 2 else 5, 15))[3] == 255, f"frame {i}: should be opaque"


@pytest.mark.parametrize("target", [ImageFormat.JPEG, ImageFormat.BMP, ImageFormat.TIFF])
def test_animation_to_still_format_uses_first_frame_and_warns(tmp_path: Path, work_dir: Path, target) -> None:
    src = make_animation(tmp_path / "anim.gif")
    result = run_one(src, work_dir, mode=Mode.CONVERT, target_format=target)
    assert result.status is Status.OK
    assert result.warnings and "анимац" in result.warnings[0].lower()
    assert frame_info(result.output_path)[0] == 1
    with Image.open(result.output_path) as out:
        r, g, b = out.convert("RGB").getpixel((35, 15))
        assert r > 200 and g < 60 and b < 60, "first (red) frame expected"


# ------------------------------------------------------------------ EXIF orientation


def jpeg_with_orientation(path: Path, orientation: int, with_gps: bool = False) -> Path:
    img = Image.new("RGB", (40, 20), (200, 30, 30))
    img.paste((30, 30, 200), (0, 0, 10, 10))  # blue marker in the top-left corner
    exif = Image.Exif()
    exif[0x0112] = orientation
    exif[0x010F] = "ACME Camera"  # Make
    if with_gps:
        exif.get_ifd(0x8825)[1] = "N"  # GPSLatitudeRef
        exif.get_ifd(0x8825)[2] = (55.0, 45.0, 0.0)
    img.save(path, "JPEG", exif=exif, quality=95)
    return path


@pytest.mark.parametrize("remove_metadata", [True, False])
@pytest.mark.parametrize("mode", [Mode.COMPRESS, Mode.CONVERT, Mode.CONVERT_COMPRESS])
def test_exif_orientation_is_applied(tmp_path: Path, work_dir: Path, mode, remove_metadata) -> None:
    src = jpeg_with_orientation(tmp_path / "rot.jpg", 6)  # needs a 90° clockwise turn
    result = run_one(src, work_dir, mode=mode, target_format=ImageFormat.PNG if mode is not Mode.COMPRESS else ImageFormat.JPEG, remove_metadata=remove_metadata)
    assert result.status is Status.OK
    assert result.output_dims == (20, 40)
    with Image.open(result.output_path) as out:
        assert out.size == (20, 40)
        assert out.getexif().get(0x0112, 1) == 1, "orientation must not be applied twice"
        r, g, b = out.convert("RGB").getpixel((15, 5))  # marker moves to the top-right
        assert b > 150 and r < 80


@pytest.mark.parametrize("orientation", range(1, 9))
def test_all_orientations(tmp_path: Path, work_dir: Path, orientation: int) -> None:
    src = jpeg_with_orientation(tmp_path / "o.jpg", orientation)
    result = run_one(src, work_dir, mode=Mode.CONVERT, target_format=ImageFormat.PNG)
    expected = (20, 40) if orientation in (5, 6, 7, 8) else (40, 20)
    assert result.output_dims == expected


# ------------------------------------------------------------------ metadata


def test_remove_metadata_strips_exif_and_gps(tmp_path: Path, work_dir: Path) -> None:
    src = jpeg_with_orientation(tmp_path / "gps.jpg", 1, with_gps=True)
    for mode in (Mode.COMPRESS, Mode.CONVERT_COMPRESS, Mode.CONVERT):
        result = run_one(src, work_dir, mode=mode, target_format=ImageFormat.JPEG, remove_metadata=True)
        assert result.output_path is not None
        with Image.open(result.output_path) as out:
            assert len(out.getexif()) == 0, f"EXIF left after {mode}"
        assert b"ACME" not in result.output_path.read_bytes()


@pytest.mark.parametrize("target", [ImageFormat.JPEG, ImageFormat.PNG, ImageFormat.WEBP])
def test_keep_metadata_preserves_exif(tmp_path: Path, work_dir: Path, target) -> None:
    src = jpeg_with_orientation(tmp_path / "keep.jpg", 1, with_gps=True)
    result = run_one(src, work_dir, mode=Mode.CONVERT, target_format=target, remove_metadata=False)
    with Image.open(result.output_path) as out:
        exif = out.getexif()
        assert exif.get(0x010F) == "ACME Camera"
        assert exif.get_ifd(0x8825).get(1) == "N"


def test_keep_metadata_preserves_exif_avif(tmp_path: Path, work_dir: Path) -> None:
    src = jpeg_with_orientation(tmp_path / "keep.jpg", 1)
    result = run_one(src, work_dir, mode=Mode.CONVERT, target_format=ImageFormat.AVIF, remove_metadata=False)
    with Image.open(result.output_path) as out:
        assert out.getexif().get(0x010F) == "ACME Camera"


def test_removed_metadata_png_text_chunks(tmp_path: Path, work_dir: Path) -> None:
    from PIL.PngImagePlugin import PngInfo

    info = PngInfo()
    info.add_text("Author", "Somebody Private")
    src = tmp_path / "text.png"
    gradient_image((64, 64)).save(src, pnginfo=info)
    result = run_one(src, work_dir, mode=Mode.COMPRESS, remove_metadata=True)
    assert b"Somebody Private" not in result.output_path.read_bytes()


# ------------------------------------------------------------------ ICC


def _icc_bytes() -> bytes:
    return ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()


@pytest.mark.parametrize("target", [ImageFormat.JPEG, ImageFormat.PNG, ImageFormat.WEBP])
def test_icc_profile_kept_or_dropped(tmp_path: Path, work_dir: Path, target) -> None:
    src = tmp_path / "icc.png"
    gradient_image((32, 32)).save(src, icc_profile=_icc_bytes())
    kept = run_one(src, work_dir, mode=Mode.CONVERT, target_format=target, remove_metadata=False)
    removed = run_one(src, work_dir / "x", mode=Mode.CONVERT, target_format=target, remove_metadata=True)
    with Image.open(kept.output_path) as out:
        assert out.info.get("icc_profile"), "ICC profile should be preserved"
    with Image.open(removed.output_path) as out:
        assert not out.info.get("icc_profile")


def _wide_gamut_profile() -> bytes | None:
    import os

    folder = Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32" / "spool" / "drivers" / "color"
    for name in ("WideGamutRGB.icc", "AdobeRGB1998.icc", "ProPhotoRGB.icc"):
        path = folder / name
        if path.exists():
            return path.read_bytes()
    return None


def test_non_srgb_profile_is_converted_when_metadata_removed(tmp_path: Path, work_dir: Path) -> None:
    icc = _wide_gamut_profile()
    if icc is None:
        pytest.skip("no wide-gamut ICC profile installed")
    img = Image.new("RGB", (16, 16), (20, 220, 40))
    src = tmp_path / "wide.png"
    img.save(src, icc_profile=icc)
    result = run_one(src, work_dir, mode=Mode.CONVERT, target_format=ImageFormat.PNG, remove_metadata=True)
    with Image.open(result.output_path) as out:
        assert not out.info.get("icc_profile")
        assert out.convert("RGB").getpixel((8, 8)) != (20, 220, 40), "pixels must be converted to sRGB"


# ------------------------------------------------------------------ "result larger than original"


def test_already_optimized_png_is_copied_unchanged(tmp_path: Path, work_dir: Path) -> None:
    src = tmp_path / "once.png"
    noise_image((64, 64)).save(src)
    first = run_one(src, work_dir / "1", mode=Mode.COMPRESS)
    optimized = tmp_path / "twice.png"
    optimized.write_bytes(first.output_path.read_bytes())
    result = run_one(optimized, work_dir / "2", mode=Mode.COMPRESS)  # nothing left to gain
    assert result.status is Status.ALREADY_OPTIMIZED
    assert result.new_size == result.original_size
    assert result.output_path.read_bytes() == optimized.read_bytes()


def test_already_optimized_jpeg_never_gets_bigger(tmp_path: Path, work_dir: Path) -> None:
    src = tmp_path / "low.jpg"
    noise_image((64, 64)).save(src, "JPEG", quality=20)  # lower quality than the preset
    result = run_one(src, work_dir, mode=Mode.COMPRESS, quality=QualityLevel.MAXIMUM)
    assert result.status in (Status.OK, Status.ALREADY_OPTIMIZED)
    assert result.new_size <= result.original_size


def test_fallback_still_strips_private_metadata(tmp_path: Path, work_dir: Path) -> None:
    """A tiny file with GPS must not be copied verbatim when metadata removal is on."""
    src = tmp_path / "private.jpg"
    exif = Image.Exif()
    exif[0x010F] = "ACME Camera"
    Image.new("RGB", (8, 8), (1, 2, 3)).save(src, "JPEG", quality=10, exif=exif)
    result = run_one(src, work_dir, mode=Mode.COMPRESS, remove_metadata=True)
    assert b"ACME" not in result.output_path.read_bytes()


def test_convert_only_may_grow(tmp_path: Path, work_dir: Path) -> None:
    src = tmp_path / "small.jpg"
    gradient_image((64, 64)).save(src, "JPEG", quality=30)
    result = run_one(src, work_dir, mode=Mode.CONVERT, target_format=ImageFormat.PNG)
    assert result.status is Status.OK  # format changed: never "already optimized"
    assert result.new_size > result.original_size


@pytest.mark.parametrize("level", list(QualityLevel))
def test_quality_levels_order(tmp_path: Path, work_dir: Path, level) -> None:
    src = tmp_path / "photo.jpg"
    noise_image((160, 160)).save(src, "JPEG", quality=98)
    result = run_one(src, work_dir / level.name, mode=Mode.COMPRESS, quality=level)
    assert result.status is Status.OK


def test_smallest_is_not_bigger_than_maximum(tmp_path: Path, work_dir: Path) -> None:
    src = tmp_path / "photo.jpg"
    noise_image((160, 160)).save(src, "JPEG", quality=98)
    sizes = {
        level: run_one(src, work_dir / level.name, mode=Mode.COMPRESS, quality=level).new_size
        for level in QualityLevel
    }
    assert sizes[QualityLevel.SMALLEST] <= sizes[QualityLevel.BALANCED] <= sizes[QualityLevel.MAXIMUM]


def test_png_lossy_is_smaller_than_lossless(tmp_path: Path, work_dir: Path) -> None:
    import random

    rnd = random.Random(7)
    base = gradient_image((192, 192))
    img = Image.new("RGB", base.size)
    img.putdata([tuple(max(0, min(255, c + rnd.randint(-6, 6))) for c in px) for px in base.getdata()])
    src = tmp_path / "textured.png"
    img.save(src)
    smallest = run_one(src, work_dir / "a", mode=Mode.COMPRESS, quality=QualityLevel.SMALLEST)
    maximum = run_one(src, work_dir / "b", mode=Mode.COMPRESS, quality=QualityLevel.MAXIMUM)
    assert smallest.status is Status.OK
    assert smallest.new_size < smallest.original_size * 0.6, "palette quantization should shrink a lot"
    assert smallest.new_size <= maximum.new_size
    with Image.open(smallest.output_path) as out:
        assert out.mode == "P", "lossy PNG should be palette based"
