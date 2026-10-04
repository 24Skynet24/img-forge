"""Every input → output format pair, modes, transparency and exotic pixel formats."""
from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from core.formats import OUTPUT_FORMATS, ImageFormat, format_info
from core.models import Status
from core.options import Mode

from .conftest import gradient_image, run_one, save_as

INPUT_FORMATS = list(ImageFormat)


def _open(path: Path) -> Image.Image:
    img = Image.open(path)
    img.load()
    return img


@pytest.mark.parametrize("target", OUTPUT_FORMATS, ids=lambda f: f.value)
@pytest.mark.parametrize("source", INPUT_FORMATS, ids=lambda f: f.value)
@pytest.mark.parametrize("mode", [Mode.CONVERT, Mode.CONVERT_COMPRESS], ids=["convert", "convert+compress"])
def test_every_format_pair(tmp_path: Path, work_dir: Path, source, target, mode) -> None:
    src = save_as(gradient_image((64, 48)), tmp_path / f"in{format_info(source).extension}", source)
    result = run_one(src, work_dir, mode=mode, target_format=target, remove_metadata=True)

    assert result.status in (Status.OK, Status.ALREADY_OPTIMIZED), result.message
    assert result.output_path is not None and result.output_path.exists()
    assert result.relative_output is not None
    assert result.relative_output.suffix.lower() in {".jpg", ".png", ".webp", ".avif", ".gif", ".bmp", ".tiff"}
    with Image.open(result.output_path) as out:
        assert out.format == {"JPEG": "JPEG", "TIFF": "TIFF"}.get(target.value, target.value)
        assert out.size == (64, 48)


def test_compress_keeps_format_and_extension(tmp_path: Path, work_dir: Path) -> None:
    src = save_as(gradient_image((300, 200)), tmp_path / "photo.jpeg", ImageFormat.JPEG, quality=100)
    result = run_one(src, work_dir, mode=Mode.COMPRESS)
    assert result.status is Status.OK
    assert result.relative_output is not None and result.relative_output.name == "photo.jpeg"
    assert result.new_size < result.original_size
    with Image.open(result.output_path) as out:
        assert out.format == "JPEG"
        assert out.info.get("progressive") or out.info.get("progression")


def test_heic_compress_only_falls_back_to_jpeg(tmp_path: Path, work_dir: Path) -> None:
    src = save_as(gradient_image((64, 48)), tmp_path / "shot.heic", ImageFormat.HEIC)
    result = run_one(src, work_dir, mode=Mode.COMPRESS)
    assert result.status is Status.OK
    assert result.output_format is ImageFormat.JPEG
    assert result.relative_output is not None and result.relative_output.suffix == ".jpg"
    assert any("JPEG" in w for w in result.warnings)


@pytest.mark.parametrize("target", [ImageFormat.JPEG, ImageFormat.BMP], ids=lambda f: f.value)
def test_transparency_is_flattened_on_background(tmp_path: Path, work_dir: Path, target) -> None:
    img = Image.new("RGBA", (20, 20), (255, 0, 0, 0))  # fully transparent red
    for x in range(10, 20):  # right half opaque green
        for y in range(20):
            img.putpixel((x, y), (0, 255, 0, 255))
    src = tmp_path / "alpha.png"
    img.save(src)
    result = run_one(src, work_dir, mode=Mode.CONVERT, target_format=target, background=(0, 0, 255))
    with Image.open(result.output_path) as out:
        out = out.convert("RGB")
        r, g, b = out.getpixel((2, 10))
        assert b > 230 and r < 25 and g < 25, "transparent area must become the blue background"
        r, g, b = out.getpixel((17, 10))
        assert g > 230 and r < 25 and b < 25, "opaque pixels must stay untouched"


@pytest.mark.parametrize("target", [ImageFormat.PNG, ImageFormat.WEBP, ImageFormat.AVIF, ImageFormat.GIF, ImageFormat.TIFF])
def test_transparency_is_preserved_when_supported(tmp_path: Path, work_dir: Path, target) -> None:
    img = Image.new("RGBA", (32, 32), (10, 200, 30, 255))
    for x in range(16):
        for y in range(32):
            img.putpixel((x, y), (0, 0, 0, 0))
    src = tmp_path / "alpha.png"
    img.save(src)
    result = run_one(src, work_dir, mode=Mode.CONVERT, target_format=target)
    with Image.open(result.output_path) as out:
        rgba = out.convert("RGBA")
        assert rgba.getpixel((3, 16))[3] < 20, "transparent pixel lost"
        assert rgba.getpixel((28, 16))[3] > 235, "opaque pixel became transparent"


def test_png_compress_preserves_transparency_and_shrinks(tmp_path: Path, work_dir: Path) -> None:
    img = gradient_image((200, 200)).convert("RGBA")
    alpha = Image.linear_gradient("L").resize((200, 200))
    img.putalpha(alpha)
    src = tmp_path / "soft.png"
    img.save(src)
    result = run_one(src, work_dir, mode=Mode.COMPRESS)
    assert result.status is Status.OK
    assert result.new_size < result.original_size
    with Image.open(result.output_path) as out:
        out = out.convert("RGBA")
        assert out.getpixel((100, 5))[3] < 40
        assert out.getpixel((100, 195))[3] > 215


@pytest.mark.parametrize(
    "mode",
    ["1", "L", "LA", "P", "PA", "RGB", "RGBA", "CMYK", "I;16", "I", "F", "YCbCr", "LAB", "HSV"],
)
@pytest.mark.parametrize("target", [ImageFormat.JPEG, ImageFormat.PNG, ImageFormat.WEBP, ImageFormat.GIF])
def test_exotic_pixel_modes_do_not_crash(tmp_path: Path, work_dir: Path, mode, target) -> None:
    base = gradient_image((32, 24))
    try:
        img = base.convert("L").convert(mode) if mode in {"I;16", "I", "F", "1", "PA"} else base.convert(mode)
    except ValueError:
        pytest.skip(f"cannot build a {mode} image")
    src = tmp_path / "exotic.tiff"
    try:
        img.save(src, "TIFF")
    except Exception:
        src = tmp_path / "exotic.png"
        try:
            img.save(src, "PNG")
        except Exception:
            pytest.skip(f"Pillow cannot store {mode}")
    try:
        _open(src)
    except Exception:
        pytest.skip(f"Pillow cannot re-read its own {mode} file")
    result = run_one(src, work_dir, mode=Mode.CONVERT_COMPRESS, target_format=target)
    assert result.status is not Status.ERROR, result.message


@pytest.mark.parametrize(
    "mode", ["1", "L", "LA", "La", "P", "PA", "RGB", "RGBA", "RGBa", "RGBX", "CMYK", "I;16", "I", "F", "YCbCr", "LAB", "HSV"]
)
def test_working_mode_normalisation(mode: str) -> None:
    from core.color import to_working_mode

    try:
        img = Image.new(mode, (4, 4))
    except ValueError:
        pytest.skip(f"cannot build a {mode} image")
    assert to_working_mode(img, None).mode in ("L", "LA", "RGB", "RGBA")


def test_16bit_grayscale_is_scaled_not_clipped(tmp_path: Path, work_dir: Path) -> None:
    img = Image.new("I;16", (8, 8), 32768)  # mid grey
    src = tmp_path / "deep.png"
    img.save(src)
    result = run_one(src, work_dir, mode=Mode.CONVERT, target_format=ImageFormat.JPEG)
    with Image.open(result.output_path) as out:
        assert 120 <= out.convert("L").getpixel((4, 4)) <= 135


def test_cmyk_jpeg_roundtrip(tmp_path: Path, work_dir: Path) -> None:
    cmyk = Image.new("CMYK", (16, 16), (0, 255, 255, 0))  # red-ish in CMYK
    src = tmp_path / "print.jpg"
    cmyk.save(src, "JPEG")
    result = run_one(src, work_dir, mode=Mode.CONVERT, target_format=ImageFormat.PNG)
    with Image.open(result.output_path) as out:
        assert out.mode in ("RGB", "RGBA")
        r, g, b = out.convert("RGB").getpixel((8, 8))
        assert r > 150 and g < 100 and b < 100


def test_original_file_is_never_modified(tmp_path: Path, work_dir: Path) -> None:
    src = save_as(gradient_image((120, 90)), tmp_path / "keep.png", ImageFormat.PNG)
    before = src.read_bytes()
    run_one(src, work_dir, mode=Mode.COMPRESS)
    run_one(src, work_dir, mode=Mode.CONVERT, target_format=ImageFormat.JPEG)
    assert src.read_bytes() == before
