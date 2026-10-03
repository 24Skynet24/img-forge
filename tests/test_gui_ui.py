"""UI-level tests for the brutalist redesign: model states, controls, frameless hit-testing, assets."""
from __future__ import annotations

import os
from pathlib import Path, PurePath

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from core.formats import ImageFormat  # noqa: E402
from core.models import FileResult, SourceItem, Status  # noqa: E402
from core.options import Mode, ProcessingOptions  # noqa: E402
from core.utils import plural  # noqa: E402
from gui import frameless  # noqa: E402

from .test_gui_smoke import app, photos, wait_until, window  # noqa: E402,F401  (fixtures)

ASSETS = Path(__file__).resolve().parent.parent / "assets"


def _item(name: str, fmt: ImageFormat = ImageFormat.JPEG) -> SourceItem:
    return SourceItem(Path(name), PurePath(name), fmt, 1000)


def _result(index: int, item: SourceItem, status: Status = Status.OK, new_size: int = 400) -> FileResult:
    return FileResult(
        index=index, status=status, source=item, original_size=item.size, new_size=new_size,
        output_format=ImageFormat.WEBP, message="boom" if status is Status.ERROR else "",
    )


@pytest.fixture
def model(app):
    from gui.widgets.queue_model import QueueModel
    from gui.widgets.thumbnails import ThumbnailCache

    m = QueueModel(ThumbnailCache(36))
    m.add_items(_item(f"{i}.jpg") for i in range(6))
    return m


def test_model_states_follow_the_batch(model) -> None:
    from gui.widgets import queue_model as qm

    assert {model.state(r) for r in range(6)} == {qm.QUEUED}
    model.set_running(True, slots=2)
    assert [model.state(r) for r in range(6)] == [qm.WORKING, qm.WORKING] + [qm.WAITING] * 4

    model.set_result(1, _result(1, model.item(1)))  # finished out of order
    assert [model.state(r) for r in range(3)] == [qm.WORKING, qm.DONE, qm.WORKING]
    model.set_result(0, _result(0, model.item(0), Status.ERROR))
    assert model.state(0) == qm.FAILED
    assert [model.state(r) for r in (2, 3, 4)] == [qm.WORKING, qm.WORKING, qm.WAITING]

    model.set_running(False)
    assert model.state(5) == qm.QUEUED and model.state(1) == qm.DONE


def test_model_predicts_target_format(model) -> None:
    model.set_options(ProcessingOptions(mode=Mode.CONVERT, target_format=ImageFormat.AVIF))
    assert model.target_format(0) is ImageFormat.AVIF
    model.set_options(ProcessingOptions(mode=Mode.COMPRESS))
    assert model.target_format(0) is ImageFormat.JPEG  # compress keeps the format
    model.set_result(0, _result(0, model.item(0)))
    assert model.target_format(0) is ImageFormat.WEBP  # the real result wins


def test_plural_forms() -> None:
    words = ("файл", "файла", "файлов")
    assert [plural(n, words) for n in (1, 2, 5, 11, 12, 21, 22, 25, 101, 111)] == [
        "файл", "файла", "файлов", "файлов", "файлов", "файл", "файла", "файлов", "файл", "файлов",
    ]


def test_stepper_clamps_and_notifies(app) -> None:
    from gui.widgets.controls import Stepper

    stepper = Stepper()
    stepper.setRange(1, 4)
    seen: list[int] = []
    stepper.valueChanged.connect(seen.append)
    stepper.setValue(99)
    stepper.setValue(-5)
    stepper.setValue(1)  # unchanged: no signal
    assert (stepper.value(), seen) == (1, [4, 1])


def test_step_slider_maps_clicks_to_levels(app) -> None:
    from gui.widgets.controls import StepSlider

    slider = StepSlider()
    slider.setRange(0, 2)
    slider.resize(212, 26)
    assert [slider._value_at(x) for x in (0, 60, 106, 160, 212)] == [0, 1, 1, 2, 2]
    assert slider._x_of(0) == StepSlider.MARGIN and slider._x_of(2) == 212 - StepSlider.MARGIN


def test_locked_panel_disables_every_control(window) -> None:
    panel = window._panel
    panel.set_locked(True)
    assert not panel.isEnabled() and not panel._workers.isEnabled()
    panel.set_locked(False)
    assert panel.isEnabled()


def test_compress_mode_disables_format_and_convert_mode_disables_level(window) -> None:
    panel = window._panel
    panel._mode_buttons[Mode.COMPRESS].setChecked(True)
    assert not panel._format.isEnabled() and panel._quality.isEnabled()
    panel._mode_buttons[Mode.CONVERT].setChecked(True)
    assert panel._format.isEnabled() and not panel._quality.isEnabled()


def test_format_dropdown_lists_every_output_format(window) -> None:
    from core.formats import OUTPUT_FORMATS

    combo = window._panel._format
    assert [combo.itemData(i) for i in range(combo.count())] == list(OUTPUT_FORMATS)
    assert combo.itemText(combo.findData(ImageFormat.WEBP)) == "WEBP"


def test_every_state_paints_in_both_themes(window, photos: Path) -> None:
    """Grab the window in each state and theme: any exception in a paintEvent fails the test."""
    for key in ("light", "dark"):
        window._set_theme(key)
        window.grab()
        window._drop_zone.set_drag_info(3, 1)
        window._set_drag_highlight(True)
        window.grab()
        window._set_drag_highlight(False)

    window.add_paths([photos])
    wait_until(lambda: window._model.rowCount() == 4 and window._scan_worker is None)
    window._panel._mode_buttons[Mode.CONVERT_COMPRESS].setChecked(True)
    window.start_processing()
    for _ in range(5):
        QApplication.processEvents()
        window.grab()
    wait_until(lambda: not window.running)

    assert window._summary_strip.isVisible() or window._last_summary is not None
    assert window._last_summary is not None and window._last_summary.errors == 1
    for key in ("light", "dark"):
        window._set_theme(key)
        window.grab()
    window.resize(960, 640)
    window.grab()  # compact layout: readouts hidden, strip squeezed
    assert not window._readouts.isVisible()
    window.resize(1240, 830)
    assert window._readouts.isVisibleTo(window)


def test_result_column_reflects_outcome(window, photos: Path) -> None:
    window.add_paths([photos])
    wait_until(lambda: window._model.rowCount() == 4 and window._scan_worker is None)
    window.start_processing()
    wait_until(lambda: not window.running)
    from gui.widgets import queue_model as qm

    states = sorted(window._model.state(r) for r in range(4))
    assert states.count(qm.FAILED) == 1 and states.count(qm.DONE) + states.count(qm.OPTIMIZED) == 3
    assert "ERR 01" in window._sources_header._right.text()


def test_removing_a_row_with_the_cross_button(window, photos: Path) -> None:
    window.add_paths([photos])
    wait_until(lambda: window._model.rowCount() == 4 and window._scan_worker is None)
    window._table.removeRequested.emit(0)
    assert window._model.rowCount() == 3
    window.clear_queue()
    assert window._stack.currentIndex() == 0


def test_title_bar_reports_the_queue(window, photos: Path) -> None:
    window.add_paths([photos])
    wait_until(lambda: window._model.rowCount() == 4 and window._scan_worker is None)
    assert "4 файла" in window._title._info.text()
    assert window.windowTitle().startswith("ImgForge")


def test_theme_switch_buttons_change_theme(window) -> None:
    window._theme_switch.chosen.emit("dark")
    assert window._theme.is_dark and window._theme_switch._dark
    window._theme_switch.chosen.emit("light")
    assert not window._theme.is_dark


# ---------------------------------------------------------------- frameless hit-testing


def _caption(pos: QPoint) -> bool:
    return pos.y() < 32 and pos.x() < 800


def test_hit_test_resize_edges_and_caption() -> None:
    size = (1000, 700)
    hit = lambda x, y, maximized=False: frameless.hit_test(QPoint(x, y), size, maximized, _caption)  # noqa: E731
    assert hit(2, 300) == frameless.HTLEFT and hit(997, 300) == frameless.HTRIGHT
    assert hit(500, 1) == frameless.HTTOP and hit(500, 698) == frameless.HTBOTTOM
    assert hit(1, 1) == frameless.HTTOPLEFT and hit(998, 1) == frameless.HTTOPRIGHT
    assert hit(1, 698) == frameless.HTBOTTOMLEFT and hit(998, 698) == frameless.HTBOTTOMRIGHT
    assert hit(400, 16) == frameless.HTCAPTION
    assert hit(900, 16) == frameless.HTCLIENT  # over the window buttons
    assert hit(500, 300) == frameless.HTCLIENT
    assert hit(2, 300, maximized=True) == frameless.HTCLIENT  # no resize borders when maximised


def test_window_is_frameless_with_minimum_size(window) -> None:
    assert window.windowFlags() & Qt.WindowType.FramelessWindowHint
    assert (window.minimumWidth(), window.minimumHeight()) == (960, 640)


# ---------------------------------------------------------------- assets


def test_bundled_fonts_load(app) -> None:
    from gui.themes import fonts

    assert fonts.load_fonts(ASSETS / "fonts")
    assert fonts._mono == "JetBrains Mono" and fonts._display == "Oswald"
    for name in ("JetBrainsMono-Regular.ttf", "JetBrainsMono-Medium.ttf", "JetBrainsMono-Bold.ttf",
                 "Oswald-SemiBold.ttf", "OFL-JetBrainsMono.txt", "OFL-Oswald.txt"):
        assert (ASSETS / "fonts" / name).exists(), name


def test_icon_has_every_size_and_is_not_the_old_tile() -> None:
    from PIL import Image

    icon = Image.open(ASSETS / "icon.ico")
    assert sorted(icon.info["sizes"]) == [(s, s) for s in (16, 24, 32, 48, 64, 128, 256)]
    big = icon.ico.getimage((256, 256)).convert("RGB")
    assert big.getpixel((128, 20)) == (0xF7, 0xF7, 0xF4)  # paper tile, not the old blue gradient
    violet = big.getpixel((200, 200))  # the last pixel of the mark is violet
    assert violet == (0x8A, 0x5C, 0xF6)


def test_window_starts_with_remembered_geometry(app, window, tmp_path: Path) -> None:
    """Regression: restoring saved geometry fired resizeEvent before the UI was built."""
    from gui.main_window import MainWindow
    from gui.settings import AppSettings

    window.resize(1100, 700)
    saved = AppSettings.load()
    saved.geometry = window.saveGeometry()
    again = MainWindow(window._theme, saved)
    assert again.width() >= 960
    again.close()


# ---------------------------------------------------------------- resizing


def test_layout_never_needs_more_than_the_window_minimum(window, photos: Path) -> None:
    """The layout's own minimum must fit inside the window minimum, in every state: otherwise the
    UI is squeezed (overlaps / clipping) as the window is shrunk."""

    def check() -> None:
        window.resize(window.minimumSize())  # the smallest the user can make it
        QApplication.processEvents()
        need = window.centralWidget().layout().minimumSize()
        assert need.width() <= window.width() and need.height() <= window.height(), need

    check()  # empty
    window.add_paths([photos])
    wait_until(lambda: window._model.rowCount() == 4 and window._scan_worker is None)
    check()  # queue
    window.start_processing()
    wait_until(lambda: not window.running)
    check()  # done, summary strip visible
    window._set_drag_highlight(True)
    check()  # drag-over wording


def test_window_cannot_be_resized_below_the_designed_minimum(window) -> None:
    window.resize(300, 300)
    QApplication.processEvents()
    assert window.width() >= 960 and window.height() >= 640


def test_top_bar_readouts_appear_only_when_they_fit(window) -> None:
    need = window._compact_need + window._readouts_extra
    for width, shown in ((960, False), (need - 1, False), (need, True), (need + 300, True)):
        window.resize(width, 800)
        QApplication.processEvents()
        assert window._readouts.isVisibleTo(window) is shown, width


def test_drop_zone_switches_to_two_lines_when_narrow(app) -> None:
    from gui.widgets.drop_zone import DropZone

    zone = DropZone()
    zone.show()
    zone.resize(1000, 500)
    QApplication.processEvents()
    assert "\n" not in zone._title.text()
    zone.resize(560, 500)
    QApplication.processEvents()
    assert "\n" in zone._title.text() and "\n" in zone._hint.text()
    zone.set_highlighted(True)
    assert "\n" in zone._title.text()
    zone.resize(1000, 500)
    QApplication.processEvents()
    assert "\n" not in zone._title.text()


def test_corner_grips_are_larger_than_edges() -> None:
    size = (1000, 700)
    hit = lambda x, y: frameless.hit_test(QPoint(x, y), size, False, _caption)  # noqa: E731
    assert hit(12, 3) == frameless.HTTOPLEFT and hit(3, 12) == frameless.HTTOPLEFT
    assert hit(997, 12) == frameless.HTTOPRIGHT and hit(988, 3) == frameless.HTTOPRIGHT
    assert hit(3, 690) == frameless.HTBOTTOMLEFT and hit(990, 697) == frameless.HTBOTTOMRIGHT
    assert hit(100, 3) == frameless.HTTOP  # away from the corner it is a plain edge
    assert frameless.EDGE >= 8
