"""Shared fixtures: small synthetic images and helpers to run the pipeline."""
from __future__ import annotations

import os
import random
import time
from collections.abc import Callable
from pathlib import Path, PurePath

import pytest
from PIL import Image

from core.formats import ImageFormat, format_info
from core.models import FileResult, SourceItem
from core.options import Mode, ProcessingOptions, QualityLevel
from core.pipeline import Task, process_file


def gradient_image(size: tuple[int, int] = (64, 48), mode: str = "RGB") -> Image.Image:
    """A colourful gradient so that compression has something to chew on."""
    w, h = size
    img = Image.new("RGB", size)
    px = img.load()
    for y in range(h):
        for x in range(w):
            px[x, y] = (x * 255 // max(1, w - 1), y * 255 // max(1, h - 1), (x + y) * 255 // (w + h))
    return img.convert(mode) if mode != "RGB" else img


def noise_image(size: tuple[int, int] = (96, 96), seed: int = 1) -> Image.Image:
    rnd = random.Random(seed)
    img = Image.new("RGB", size)
    img.putdata([(rnd.randrange(256), rnd.randrange(256), rnd.randrange(256)) for _ in range(size[0] * size[1])])
    return img


def save_as(img: Image.Image, path: Path, fmt: ImageFormat, **kwargs) -> Path:
    """Write ``img`` to ``path`` in ``fmt`` (HEIC is skipped when no encoder is available)."""
    if fmt is ImageFormat.HEIC:
        try:
            img.save(path, "HEIF", quality=90, **kwargs)
        except Exception:
            pytest.skip("HEIC encoder is not available")
        return path
    if fmt is ImageFormat.JPEG:
        img = img.convert("RGB")
    img.save(path, fmt.value, **kwargs)
    return path


def make_item(path: Path, relative: str | None = None) -> SourceItem:
    from core.formats import format_from_path

    fmt = format_from_path(path)
    assert fmt is not None
    return SourceItem(
        path=path, relative=PurePath(relative or path.name), format=fmt, size=path.stat().st_size
    )


def run_one(path: Path, work_dir: Path, **option_kwargs) -> FileResult:
    """Process a single file in-process."""
    options = ProcessingOptions(workers=1, **option_kwargs)
    work_dir.mkdir(parents=True, exist_ok=True)
    return process_file(Task(0, make_item(path), options, work_dir))


@pytest.fixture
def work_dir(tmp_path: Path) -> Path:
    path = tmp_path / "work"
    path.mkdir()
    return path


__all__ = [
    "gradient_image", "noise_image", "save_as", "make_item", "run_one",
    "Mode", "QualityLevel", "ImageFormat", "format_info",
]


# --------------------------------------------------------------------------- GUI fixtures

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def app():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    instance = QApplication.instance() or QApplication(["imgforge-test"])
    instance.setStyle("Fusion")
    # the real app runs with the bundled fonts; layout minimums depend on their metrics
    from gui.themes.fonts import app_font, load_fonts

    load_fonts(Path(__file__).resolve().parent.parent / "assets" / "fonts")
    instance.setFont(app_font())
    return instance


def wait_until(condition: Callable[[], bool], timeout: float = 60.0) -> None:
    from PySide6.QtWidgets import QApplication

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        QApplication.processEvents()
        if condition():
            return
        time.sleep(0.01)
    raise AssertionError("timed out waiting for the GUI")


@pytest.fixture
def window(app, tmp_path: Path, monkeypatch):
    from PySide6.QtCore import QSettings

    from gui.main_window import MainWindow
    from gui.settings import AppSettings
    from gui.themes.manager import ThemeManager

    ini = tmp_path / "settings.ini"
    monkeypatch.setattr(
        AppSettings, "_store", staticmethod(lambda: QSettings(str(ini), QSettings.Format.IniFormat))
    )
    settings = AppSettings.load()
    theme = ThemeManager(app, settings.theme)
    theme.apply()
    win = MainWindow(theme, settings)
    win.show()
    yield win
    win.close()


@pytest.fixture
def photos(tmp_path: Path) -> Path:
    root = tmp_path / "Photos"
    (root / "nested" / "deeper").mkdir(parents=True)
    save_as(gradient_image((300, 200)), root / "a.jpg", ImageFormat.JPEG, quality=98)
    save_as(gradient_image((120, 120)), root / "nested" / "b.png", ImageFormat.PNG)
    save_as(gradient_image((64, 64)), root / "nested" / "deeper" / "c.bmp", ImageFormat.BMP)
    (root / "readme.txt").write_text("not an image")
    (root / "broken.jpg").write_bytes(b"garbage")
    return root
