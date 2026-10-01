"""Headless GUI smoke test: drives the real window through scan → process → compare → save."""
from __future__ import annotations

import os
import time
from collections.abc import Callable
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtGui import QKeySequence  # noqa: E402
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox  # noqa: E402

from imgforge.core.formats import ImageFormat  # noqa: E402
from imgforge.core.models import Status  # noqa: E402
from imgforge.core.options import Mode  # noqa: E402
from imgforge.core.saver import ConflictAction  # noqa: E402
from imgforge.gui.settings import AppSettings  # noqa: E402

from .conftest import gradient_image, save_as  # noqa: E402


@pytest.fixture(scope="module")
def app() -> QApplication:
    instance = QApplication.instance() or QApplication(["imgforge-test"])
    instance.setStyle("Fusion")
    return instance


def wait_until(condition: Callable[[], bool], timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        QApplication.processEvents()
        if condition():
            return
        time.sleep(0.01)
    raise AssertionError("timed out waiting for the GUI")


@pytest.fixture
def window(app, tmp_path: Path, monkeypatch):
    from imgforge.gui.main_window import MainWindow
    from imgforge.gui.themes.manager import ThemeManager

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


def test_full_flow(window, photos: Path, tmp_path: Path, monkeypatch) -> None:
    window.add_paths([photos])
    wait_until(lambda: window._model.rowCount() == 4 and window._scan_worker is None)
    assert window._skipped == 1  # readme.txt
    assert window._stack.currentIndex() == 1

    # Choose "Convert + compress → WebP" like a user would.
    window._panel._mode_buttons[Mode.CONVERT_COMPRESS].setChecked(True)
    window._panel._format.setCurrentIndex(window._panel._format.findData(ImageFormat.WEBP))
    window.start_processing()
    assert window.running
    wait_until(lambda: not window.running)

    results = window._model.results()
    assert len(results) == 4
    assert sorted(r.status.value for r in results) == ["error", "ok", "ok", "ok"]
    assert "Готово" in window._info.text()
    assert window._btn_save.isEnabled() and window._btn_log.isEnabled()

    # Compare view for a processed image.
    ok = next(r for r in results if r.status is Status.OK)
    window._open_compare(ok)
    dialog = window._compare_dialogs[-1]
    wait_until(lambda: dialog._view.isVisible() and dialog._view._original is not None)
    dialog._view.actual_size()
    dialog._view.fit()
    dialog.grab()  # force a paint with the split line
    dialog.close()

    # Save, with an existing folder at the destination -> conflict dialog -> "rename".
    dest = tmp_path / "dest"
    (dest / "Photos").mkdir(parents=True)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(dest))
    from imgforge.gui import main_window as mw

    class AutoRename:
        def __init__(self, *_a, **_k) -> None:
            self.action = ConflictAction.RENAME
            self.apply_to_all = True

        def exec(self) -> int:
            return 1

    monkeypatch.setattr(mw, "ConflictDialog", AutoRename)
    monkeypatch.setattr(QMessageBox, "exec", lambda self: 0)
    window.save_results()
    wait_until(lambda: not window.saving)
    assert (dest / "Photos_1" / "a.webp").exists()
    assert (dest / "Photos_1" / "nested" / "b.webp").exists()
    assert (dest / "Photos_1" / "nested" / "deeper" / "c.webp").exists()
    assert window._btn_open.isEnabled()

    # Export log.
    log = tmp_path / "log.txt"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(log), ""))
    window.export_log()
    assert "broken.jpg" in log.read_text(encoding="utf-8")

    # Remove and clear.
    window._table.selectRow(0)
    window.remove_selected()
    assert window._model.rowCount() == 3
    window.clear_queue()
    assert window._model.rowCount() == 0 and window._stack.currentIndex() == 0


def test_cancel_keeps_finished_results(window, tmp_path: Path) -> None:
    folder = tmp_path / "many"
    folder.mkdir()
    for i in range(30):
        save_as(gradient_image((400, 400)), folder / f"{i:02d}.png", ImageFormat.PNG)
    window.add_paths([folder])
    wait_until(lambda: window._model.rowCount() == 30 and window._scan_worker is None)
    window._panel._workers.setValue(2)
    window.start_processing()
    wait_until(lambda: window._done >= 1)
    window.cancel_processing()
    wait_until(lambda: not window.running)
    assert 1 <= len(window._model.results()) < 30
    assert "Отменено" in window._info.text()


def test_settings_are_remembered(window, app, tmp_path: Path) -> None:
    window._panel._mode_buttons[Mode.CONVERT].setChecked(True)
    window._panel._format.setCurrentIndex(window._panel._format.findData(ImageFormat.AVIF))
    window._panel._metadata.setChecked(False)
    window._panel._quality.setValue(2)
    window._set_theme("dark")
    reloaded = AppSettings.load()
    assert reloaded.mode is Mode.CONVERT
    assert reloaded.target_format is ImageFormat.AVIF
    assert reloaded.remove_metadata is False
    assert int(reloaded.quality) == 2
    assert reloaded.theme == "dark"
    assert window._theme.is_dark
    window._set_theme("light")
    assert not window._theme.is_dark


def test_shortcuts_are_registered(window) -> None:
    keys = {a.shortcut().toString() for a in window.actions()} | {
        s.toString() for a in window.actions() for s in a.shortcuts()
    }
    assert {"Ctrl+O", "Ctrl+Shift+O", "Ctrl+Return", "Ctrl+Enter", "Ctrl+S"} <= keys
    assert any(QKeySequence("Delete") in a.shortcuts() for a in window._table.actions())
