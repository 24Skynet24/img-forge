"""The main application window."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from PySide6.QtCore import QModelIndex, QPoint, Qt, QTimer, QUrl
from PySide6.QtGui import (
    QAction,
    QCloseEvent,
    QDesktopServices,
    QDragEnterEvent,
    QDragLeaveEvent,
    QDropEvent,
    QIcon,
    QKeySequence,
    QPainter,
)
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QMainWindow,
    QMenu,
    QMessageBox,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.formats import INPUT_EXTENSIONS
from core.models import FileResult, Summary, summarize
from core.options import Mode, ProcessingOptions, QualityLevel
from core.pipeline import BatchOutcome
from core.report import format_log
from core.saver import SaveEntry, SaveReport
from core.scanner import ScanResult
from core.utils import format_duration, format_size, plural
from gui import frameless
from gui.compare_view import CompareDialog
from gui.settings import AppSettings
from gui.themes.manager import ThemeManager
from gui.widgets.conflict_dialog import ConflictDialog
from gui.widgets.controls import ThemeSwitch
from gui.widgets.drop_zone import DropStrip, DropZone
from gui.widgets.kit import Btn, ElidedTx, Header, MarkWidget, Surface, Tx, col, draw_frame
from gui.widgets.queue_model import QueueModel
from gui.widgets.queue_view import QueueList
from gui.widgets.run_panel import RunPanel
from gui.widgets.settings_panel import SettingsPanel
from gui.widgets.summary_strip import SummaryStrip
from gui.widgets.thumbnails import ThumbnailCache
from gui.widgets.title_bar import TitleBar
from gui.workers import ProcessWorker, SaveWorker, ScanWorker

THUMB_SIZE = 36
MIN_WIDTH, MIN_HEIGHT = 960, 640  # the designed minimum window size
_QUALITY_TAGS = {QualityLevel.MAXIMUM: "MAX", QualityLevel.BALANCED: "BAL", QualityLevel.SMALLEST: "MIN"}
_FILES = ("файл", "файла", "файлов")


def _file_filter() -> str:
    patterns = " ".join(f"*{ext}" for ext in sorted(INPUT_EXTENSIONS))
    return f"Изображения ({patterns});;Все файлы (*.*)"


class _Readout(Surface):
    """``SYS.QUEUE / 024 / 214.7 MB`` cell of the top bar."""

    def __init__(self, title: str, width: int, parent: QWidget | None = None) -> None:
        super().__init__(None, left="line", parent=parent)
        self.setFixedWidth(width)  # fixed: a changing value must never change the layout
        self._value = ElidedTx("", 11, 700)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 0, 14, 0)
        layout.setSpacing(3)
        layout.addStretch()
        layout.addWidget(Tx(title, 9, tone="mute", spacing=0.1))
        layout.addWidget(self._value)
        layout.addStretch()

    def set_value(self, text: str) -> None:
        self._value.setText(text)


class _StatusDot(QWidget):
    """8 px square: empty / ink / violet / lime depending on what the app is doing."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(8, 8)
        self._fill: str | None = None

    def set_fill(self, token: str | None) -> None:
        self._fill = token
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        if self._fill:
            p.fillRect(self.rect(), col(self._fill))
        draw_frame(p, self.rect(), col("ink"))
        p.end()


class MainWindow(QMainWindow):
    """Queue, settings, progress, results and the save/compare actions."""

    def __init__(self, theme: ThemeManager, settings: AppSettings, icon: QIcon | None = None) -> None:
        super().__init__()
        self._theme = theme
        self._settings = settings
        self.setWindowTitle("ImgForge")
        if icon is not None:
            self.setWindowIcon(icon)
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowMinMaxButtonsHint
            | Qt.WindowType.WindowSystemMenuHint
        )
        self.setAcceptDrops(True)
        self.resize(1240, 830)

        # State
        self._work_dir: Path | None = None
        self._scan_worker: ScanWorker | None = None
        self._pending_scans: list[Path] = []
        self._process_worker: ProcessWorker | None = None
        self._save_worker: SaveWorker | None = None
        self._last_saved_dir: Path | None = None
        self._last_options: ProcessingOptions | None = None
        self._last_elapsed = 0.0
        self._skipped = 0
        self._duplicates = 0
        self._summary_text = ""
        self._last_summary: Summary | None = None
        self._cancelled = False
        self._done = 0
        self._total = 0
        self._bytes_done = 0
        self._bytes_total = 0
        self._started_at = 0.0
        self._compare_dialogs: list[CompareDialog] = []
        self._frame_ready = False

        self._thumbs = ThumbnailCache(THUMB_SIZE, parent=self)
        self._model = QueueModel(self._thumbs, self)

        self._build_ui()
        self._build_actions()
        self._timer = QTimer(self)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self._tick)
        self._anim = QTimer(self)
        self._anim.setInterval(90)
        self._anim.timeout.connect(self._animate)
        theme.changed.connect(self._on_theme_changed)
        self._on_settings_changed(save=False)
        self._on_theme_changed(theme.tokens)
        self._refresh_state()
        self._fit_minimum_size()
        if settings.geometry is not None:  # after the UI exists: restoring resizes the window
            self.restoreGeometry(settings.geometry)

    # ================================================================== construction

    def _build_ui(self) -> None:
        root = Surface("bg", top="ink", bottom="ink", left="ink", right="ink")
        self.setCentralWidget(root)

        self._title = TitleBar()
        self._title.minimizeRequested.connect(self.showMinimized)
        self._title.maximizeRequested.connect(self._toggle_maximized)
        self._title.closeRequested.connect(self.close)

        # ---- top bar
        self._btn_add_files = Btn("Добавить файлы", "+")
        self._btn_add_folder = Btn("Добавить папку", "+")
        self._btn_clear = Btn("Очистить", "✕", kind="ghost")

        brand = Surface(None, right="line")
        brand_layout = QHBoxLayout(brand)
        brand_layout.setContentsMargins(20, 0, 20, 0)
        brand_layout.setSpacing(10)
        brand_layout.addWidget(MarkWidget(22, hole="bg"))
        brand_layout.addWidget(Tx("IMGFORGE", 21, 600, display=True, spacing=0.03))
        brand_layout.addSpacing(-10)
        brand_layout.addWidget(Tx("_", 21, 600, "vtext", display=True))

        buttons = QWidget()
        buttons_layout = QHBoxLayout(buttons)
        buttons_layout.setContentsMargins(16, 0, 16, 0)
        buttons_layout.setSpacing(8)
        for button in (self._btn_add_files, self._btn_add_folder, self._btn_clear):
            buttons_layout.addWidget(button)

        self._ro_queue = _Readout("SYS.QUEUE", 150)
        self._ro_out = _Readout("OUT.FMT", 112)
        self._ro_thr = _Readout("THR", 76)
        self._readouts = QWidget()
        readouts_layout = QHBoxLayout(self._readouts)
        readouts_layout.setContentsMargins(0, 0, 0, 0)
        readouts_layout.setSpacing(0)
        for readout in (self._ro_queue, self._ro_out, self._ro_thr):
            readouts_layout.addWidget(readout)

        self._theme_switch = ThemeSwitch()
        self._theme_switch.chosen.connect(self._set_theme)
        theme_box = Surface(None, left="line")
        theme_layout = QHBoxLayout(theme_box)
        theme_layout.setContentsMargins(16, 0, 16, 0)
        theme_layout.setSpacing(10)
        theme_layout.addWidget(Tx("Тема", 10, tone="mute", spacing=0.1, upper=True))
        theme_layout.addWidget(self._theme_switch)

        top = Surface("bg", bottom="ink")
        top.setFixedHeight(52)
        top_layout = QHBoxLayout(top)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(0)
        top_layout.addWidget(brand)
        top_layout.addWidget(buttons)
        top_layout.addStretch()
        top_layout.addWidget(self._readouts)
        top_layout.addWidget(theme_box)

        # ---- queue / results table
        self._queue = QueueList(self._model)
        self._table = self._queue.view
        self._table.removeRequested.connect(self._remove_row)

        self._drop_zone = DropZone()
        self._summary_strip = SummaryStrip()
        self._summary_strip.hide()
        self._drop_strip = DropStrip()
        self._strip_holder = QWidget()
        strip_layout = QHBoxLayout(self._strip_holder)
        strip_layout.setContentsMargins(16, 0, 16, 12)
        strip_layout.addWidget(self._drop_strip)

        rows_page = QWidget()
        rows_layout = QVBoxLayout(rows_page)
        rows_layout.setContentsMargins(0, 0, 0, 0)
        rows_layout.setSpacing(0)
        rows_layout.addWidget(self._summary_strip)
        rows_layout.addWidget(self._queue, 1)
        rows_layout.addWidget(self._strip_holder)

        self._stack = QStackedWidget()
        self._stack.addWidget(self._drop_zone)
        self._stack.addWidget(rows_page)

        self._sources_header = Header("/01", "ИСТОЧНИКИ")
        header_box = Surface(None, bottom="line")
        header_box.setFixedHeight(40)
        header_layout = QHBoxLayout(header_box)
        header_layout.setContentsMargins(16, 0, 16, 0)
        header_layout.addWidget(self._sources_header)

        left = Surface("panel", right="ink")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 1, 0)
        left_layout.setSpacing(0)
        left_layout.addWidget(header_box)
        left_layout.addWidget(self._stack, 1)

        # ---- right column: settings (scrolls) + launch block
        self._panel = SettingsPanel(self._settings)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(self._panel)
        scroll.viewport().setAutoFillBackground(False)
        self._run = RunPanel()

        right = Surface("panel")
        right.setFixedWidth(352)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        right_layout.addWidget(scroll, 1)
        right_layout.addWidget(self._run)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(left, 1)
        body.addWidget(right)

        # ---- status bar
        self._dot = _StatusDot()
        self._info = ElidedTx("", 12)
        self._btn_compare = Btn("Сравнить", "↔", kind="status", height=32, px=11)
        self._btn_log = Btn("Экспорт лога", "↓", kind="status", height=32, px=11)
        self._btn_open = Btn("Открыть папку", "↗", kind="status", height=32, px=11)
        self._btn_save = Btn("Сохранить…", "→", kind="status", height=32, px=11)
        status = Surface("bg", top="ink")
        status.setFixedHeight(56)
        status_layout = QHBoxLayout(status)
        status_layout.setContentsMargins(16, 12, 12, 12)
        status_layout.setSpacing(6)
        status_layout.addWidget(self._dot)
        status_layout.addSpacing(4)
        status_layout.addWidget(self._info, 1)
        for button in (self._btn_compare, self._btn_log, self._btn_open, self._btn_save):
            status_layout.addWidget(button)

        layout = QVBoxLayout(root)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)
        layout.addWidget(self._title)
        layout.addWidget(top)
        layout.addLayout(body, 1)
        layout.addWidget(status)

        self._btn_start = self._run.start
        self._btn_cancel = self._run.cancel
        self._top_layout = top_layout

        # Wiring
        self._btn_add_files.clicked.connect(self.add_files_dialog)
        self._btn_add_folder.clicked.connect(self.add_folder_dialog)
        self._btn_clear.clicked.connect(self.clear_queue)
        self._btn_start.clicked.connect(self.start_processing)
        self._btn_cancel.clicked.connect(self.cancel_processing)
        self._btn_compare.clicked.connect(self._compare_selected)
        self._btn_save.clicked.connect(self.save_results)
        self._btn_open.clicked.connect(self.open_saved_folder)
        self._btn_log.clicked.connect(self.export_log)
        self._drop_zone.addFilesRequested.connect(self.add_files_dialog)
        self._drop_zone.addFolderRequested.connect(self.add_folder_dialog)
        self._drop_strip.clicked.connect(self.add_files_dialog)
        self._table.doubleClicked.connect(self._on_double_click)
        self._table.customContextMenuRequested.connect(self._context_menu)
        self._table.selectionModel().selectionChanged.connect(lambda *_: self._refresh_state())
        self._panel.changed.connect(self._on_settings_changed)

    def _build_actions(self) -> None:
        def make(text: str, shortcuts: list[str], slot, owner: QWidget | None = None) -> QAction:
            action = QAction(text, self)
            action.setShortcuts([QKeySequence(s) for s in shortcuts])
            action.triggered.connect(slot)
            (self if owner is None else owner).addAction(action)
            return action

        make("Добавить файлы", ["Ctrl+O"], self.add_files_dialog)
        make("Добавить папку", ["Ctrl+Shift+O"], self.add_folder_dialog)
        make("Начать", ["Ctrl+Return", "Ctrl+Enter"], self.start_processing)
        make("Сохранить", ["Ctrl+S"], self.save_results)
        remove = make("Удалить выбранные", ["Delete"], self.remove_selected, self._table)
        remove.setShortcutContext(Qt.ShortcutContext.WidgetShortcut)
        self._btn_add_files.setToolTip("Ctrl+O")
        self._btn_add_folder.setToolTip("Ctrl+Shift+O")
        self._btn_start.setToolTip("Ctrl+Enter")
        self._btn_save.setToolTip("Ctrl+S")
        self._btn_clear.setToolTip("Очистить очередь")

    # ================================================================== frameless window

    def _toggle_maximized(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if not self._frame_ready:
            self._frame_ready = True
            frameless.enable_native_frame(self)

    def changeEvent(self, event) -> None:  # noqa: N802
        super().changeEvent(event)
        if event.type() == event.Type.WindowStateChange:
            self._title.set_maximized(self.isMaximized())

    def _fit_minimum_size(self) -> None:
        """Window minimum = what the layout needs (never squeezed), but at least the designed 960 × 640.

        The top-bar readouts are optional: they are shown only when there is room for them, so the
        minimum is measured without them.
        """
        self._readouts.hide()
        layout = self.centralWidget().layout()
        layout.activate()
        need = layout.minimumSize()
        self.setMinimumSize(max(MIN_WIDTH, need.width()), max(MIN_HEIGHT, need.height()))
        self._readouts_extra = self._readouts.sizeHint().width()
        self._readouts.setVisible(self.width() >= need.width() + self._readouts_extra)
        self._compact_need = need.width()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if hasattr(self, "_compact_need"):
            show = self.width() >= self._compact_need + self._readouts_extra
            if show != self._readouts.isVisibleTo(self):
                self._readouts.setVisible(show)

    def _in_caption(self, pos: QPoint) -> bool:
        local = self._title.mapFrom(self, pos)
        return self._title.rect().contains(local) and self._title.is_caption_at(local)

    def nativeEvent(self, event_type, message):  # noqa: N802
        if event_type == b"windows_generic_MSG":
            handled = frameless.handle_native_event(self, message, self._in_caption)
            if handled is not None:
                return handled
        return super().nativeEvent(event_type, message)

    # ================================================================== state

    @property
    def running(self) -> bool:
        return self._process_worker is not None

    @property
    def saving(self) -> bool:
        return self._save_worker is not None

    def _refresh_state(self) -> None:
        has_items = self._model.rowCount() > 0
        results = self._model.results()
        has_results = any(r.ok for r in results)
        busy = self.running or self.saving
        self._stack.setCurrentIndex(1 if has_items else 0)
        self._btn_start.setEnabled(has_items and not busy)
        self._run.set_running(self.running)
        self._btn_save.setEnabled(has_results and not busy)
        self._btn_log.setEnabled(bool(results) and not busy)
        self._btn_open.setEnabled(self._last_saved_dir is not None and self._last_saved_dir.exists())
        self._btn_clear.setEnabled(has_items and not busy)
        self._btn_add_files.setEnabled(not self.running)
        self._btn_add_folder.setEnabled(not self.running)
        self._drop_zone.setEnabled(not self.running)
        self._strip_holder.setVisible(not self.running)
        self._table.set_removable(not busy)
        self._panel.set_locked(self.running)
        self._btn_compare.setEnabled(self._selected_result() is not None)
        self._summary_strip.setVisible(self._last_summary is not None and not self.running)
        self._update_info()
        self._update_chrome()

    def _update_info(self) -> None:
        """The status-bar sentence (scan / progress texts are set where they happen)."""
        if self.running or self._scan_worker is not None:
            return
        parts: list[str] = []
        if self._summary_text:
            parts.append(self._summary_text)
        else:
            n = self._model.rowCount()
            if n:
                parts.append(
                    f"{n} {plural(n, _FILES)} · {format_size(self._model.total_source_size())} · готово к запуску"
                )
            else:
                parts.append("Очередь пуста")
        if self._skipped:
            parts.append(f"пропущено не-изображений: {self._skipped}")
        if self._duplicates:
            parts.append(f"уже в очереди: {self._duplicates}")
        self._info.setText(" · ".join(parts))

    def _percent(self) -> int:
        return 100 * self._done // self._total if self._total else 0

    def _update_chrome(self) -> None:
        """Title bar, /01 header, top-bar readouts, /04 info and the status dot."""
        n = self._model.rowCount()
        size = format_size(self._model.total_source_size())
        options = self._panel.options()
        summary = self._last_summary
        files = plural(n, _FILES)

        if self.running:
            title = f"— обработка {self._percent()}%"
            source = f"ОБРАБОТКА {self._done} / {self._total}"
            start = f"THR {self._busy_threads(options)} / {options.workers}"
            dot: str | None = "violet"
        elif summary is not None:
            title = f"— готово · {self._saved_text(summary)}"
            source = f"ГОТОВО {summary.ok + summary.already_optimized} / {summary.total} · ERR {summary.errors:02d}"
            start = f"ПОВТОР · {n:03d} {files.upper()}"
            dot = "lime"
        elif n:
            title = f"— {n} {files} · {size}"
            source = f"FILES {n:03d} · {size} · DIRS {self._model.folder_count()}"
            start = f"{n:03d} {files.upper()} → {self._target_tag(options)}"
            dot = "ink"
        else:
            title, source, start, dot = "", "FILES 000 · DEPTH —", "НЕТ ФАЙЛОВ", None
        if self._drop_zone.highlighted:
            dot = "violet"
        self._title.set_info(title)
        self.setWindowTitle(f"ImgForge {title}".strip())
        self._sources_header.set_right(source)
        self._run.set_info(start)
        self._dot.set_fill(dot)

        out = self._target_tag(options)
        self._ro_queue.set_value(f"{n:03d} / {size}" if n else "000 / 0 Б")
        self._ro_out.set_value(f"{out} · {self._quality_tag(options)}")
        self._ro_thr.set_value(
            f"{self._busy_threads(options)} / {options.workers}" if self.running else str(options.workers)
        )
        self._drop_zone.set_readout(f"OUT → {out} · THR {options.workers}")
        self._drop_strip.set_count(f"{n:03d} В ОЧЕРЕДИ")

    def _busy_threads(self, options: ProcessingOptions) -> int:
        return max(1, min(options.workers, self._total - self._done))

    @staticmethod
    def _saved_text(summary: Summary) -> str:
        pct = summary.saved_percent
        return f"−{pct:.1f}%" if pct >= 0 else f"+{abs(pct):.1f}%"

    @staticmethod
    def _target_tag(options: ProcessingOptions) -> str:
        return "ИСХ." if options.mode is Mode.COMPRESS else options.target_format.value

    @staticmethod
    def _quality_tag(options: ProcessingOptions) -> str:
        return "—" if options.mode is Mode.CONVERT else _QUALITY_TAGS[options.quality]

    def _on_theme_changed(self, tokens) -> None:
        self._theme_switch.set_dark(self._theme.is_dark)
        for dialog in self._compare_dialogs:
            dialog.set_tokens(tokens)
        self.update()

    def _set_theme(self, key: str) -> None:
        self._settings.theme = key
        self._theme.set_preference(key)
        self._settings.save()

    def _on_settings_changed(self, save: bool = True) -> None:
        options = self._panel.options()
        self._model.set_options(options)
        if save:
            self._settings.update_from(options)
            self._settings.save()
        self._update_chrome()

    # ================================================================== adding files

    def add_files_dialog(self) -> None:
        if self.running:
            return
        files, _ = QFileDialog.getOpenFileNames(
            self, "Выберите изображения", self._settings.last_dir, _file_filter()
        )
        if files:
            self._settings.last_dir = str(Path(files[0]).parent)
            self.add_paths([Path(f) for f in files])

    def add_folder_dialog(self) -> None:
        if self.running:
            return
        folder = QFileDialog.getExistingDirectory(self, "Выберите папку с изображениями", self._settings.last_dir)
        if folder:
            self._settings.last_dir = str(Path(folder).parent)
            self.add_paths([Path(folder)])

    def add_paths(self, paths: list[Path]) -> None:
        """Scan files/folders in the background and append the images to the queue."""
        if self.running or not paths:
            return
        if self._scan_worker is not None:
            self._pending_scans.extend(paths)
            return
        worker = ScanWorker(paths, [i.path for i in self._model.items()], self)
        worker.progress.connect(lambda n: self._info.setText(f"Сканирование… найдено изображений: {n}"))
        worker.done.connect(self._on_scan_done)
        self._scan_worker = worker
        self._info.setText("Сканирование…")
        worker.start()

    def _on_scan_done(self, result: ScanResult) -> None:
        worker, self._scan_worker = self._scan_worker, None
        if worker is not None:
            worker.wait()
            worker.deleteLater()
        self._skipped += result.skipped
        self._duplicates += result.duplicates
        if self._model.add_items(result.items):
            self._summary_text = ""  # the old summary no longer describes the queue
            self._last_summary = None
        if self._pending_scans:
            pending, self._pending_scans = self._pending_scans, []
            self.add_paths(pending)
        self._refresh_state()

    def clear_queue(self) -> None:
        if self.running or self.saving:
            return
        self._model.clear()
        self._cleanup_work_dir()
        self._skipped = self._duplicates = 0
        self._summary_text = ""
        self._last_summary = None
        self._total = self._done = 0
        self._last_saved_dir = None
        self._refresh_state()

    def remove_selected(self) -> None:
        if self.running or self.saving:
            return
        rows = [i.row() for i in self._table.selectionModel().selectedRows()]
        if rows:
            self._remove_rows(rows)

    def _remove_row(self, row: int) -> None:
        if not (self.running or self.saving):
            self._remove_rows([row])

    def _remove_rows(self, rows: list[int]) -> None:
        self._model.remove_rows(rows)
        self._summary_text = ""
        self._last_summary = None
        self._refresh_state()

    # ----- drag & drop

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if not self.running and event.mimeData().hasUrls():
            event.acceptProposedAction()
            paths = [Path(u.toLocalFile()) for u in event.mimeData().urls() if u.isLocalFile()]
            dirs = sum(1 for p in paths if p.is_dir())
            self._drop_zone.set_drag_info(len(paths) - dirs, dirs)
            self._set_drag_highlight(True)
        else:
            event.ignore()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:  # noqa: N802
        self._set_drag_highlight(False)

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        self._set_drag_highlight(False)
        paths = [Path(u.toLocalFile()) for u in event.mimeData().urls() if u.isLocalFile()]
        if paths:
            event.acceptProposedAction()
            self.add_paths(paths)

    def _set_drag_highlight(self, on: bool) -> None:
        self._drop_zone.set_highlighted(on)
        self._drop_strip.set_highlighted(on)
        self._update_chrome()

    # ================================================================== processing

    def start_processing(self) -> None:
        if self.running or self.saving or self._model.rowCount() == 0:
            return
        options = self._panel.options()
        self._settings.update_from(options)
        self._settings.save()
        self._last_options = options
        self._cleanup_work_dir()
        self._work_dir = Path(tempfile.mkdtemp(prefix="imgforge_"))
        self._model.clear_results()
        items = self._model.items()
        self._summary_text = ""
        self._last_summary = None
        self._cancelled = False
        self._total, self._done = len(items), 0
        self._bytes_total = sum(i.size for i in items) or 1
        self._bytes_done = 0
        self._started_at = time.monotonic()
        worker = ProcessWorker(items, options, self._work_dir, self)
        worker.resultReady.connect(self._on_result)
        worker.finishedAll.connect(self._on_process_finished)
        worker.failed.connect(self._on_process_failed)
        self._process_worker = worker
        self._model.set_running(True, options.workers)
        self._info.setText(f"Обработка: {self._total} {plural(self._total, _FILES)}, потоков: {options.workers}")
        self._timer.start()
        self._anim.start()
        self._tick()
        worker.start()
        self._refresh_state()

    def cancel_processing(self) -> None:
        if self._process_worker is not None:
            self._cancelled = True
            self._process_worker.cancel()
            self._btn_cancel.setEnabled(False)
            self._info.setText("Отмена… дожидаемся завершения файлов в работе")

    def _on_result(self, result: FileResult) -> None:
        self._model.set_result(result.index, result)
        self._done += 1
        self._bytes_done += result.source.size
        self._update_progress()
        self._update_chrome()

    def _animate(self) -> None:
        self._table.advance()
        self._run.advance()

    def _tick(self) -> None:
        if self.running:
            self._update_progress()

    def _update_progress(self) -> None:
        options = self._last_options
        elapsed = time.monotonic() - self._started_at
        fraction = self._bytes_done / self._bytes_total
        threads = self._busy_threads(options) if options else 0
        meta = f"THR {threads}/{options.workers if options else 0} · {format_duration(elapsed)}"
        if fraction >= 0.02 and self._done < self._total:
            meta += f" · ETA {format_duration(elapsed * (1 - fraction) / fraction)}"
        inflight = min(options.workers if options else 1, self._total - self._done)
        self._run.set_progress(self._done, self._total, inflight, meta)

    def _on_process_finished(self, outcome: BatchOutcome) -> None:
        self._finish_worker()
        self._last_elapsed = outcome.elapsed
        s = summarize(outcome.results)
        self._last_summary = s
        head = (
            f"Отменено: обработано {s.total} из {self._total}"
            if outcome.cancelled
            else f"Готово: {s.ok + s.already_optimized} из {s.total}"
        )
        tail = f" · ошибок: {s.errors}" if s.errors else ""
        self._summary_text = (
            f"{head}{tail} · сэкономлено {format_size(s.saved_bytes)} ({s.saved_percent:.1f}%)"
        )
        self._summary_strip.set_summary(s, outcome.elapsed)
        self._refresh_state()

    def _on_process_failed(self, message: str) -> None:
        self._finish_worker()
        self._summary_text = f"Обработка прервана: {message}"
        self._refresh_state()

    def _finish_worker(self) -> None:
        worker, self._process_worker = self._process_worker, None
        self._timer.stop()
        self._anim.stop()
        self._model.set_running(False)
        self._btn_cancel.setEnabled(True)
        if worker is not None:
            worker.wait()
            worker.deleteLater()

    # ================================================================== saving

    def save_results(self) -> None:
        if self.running or self.saving:
            return
        entries = [
            SaveEntry(r.output_path, r.relative_output)
            for r in self._model.results()
            if r.ok and r.output_path is not None and r.relative_output is not None
        ]
        if not entries:
            return
        dest = QFileDialog.getExistingDirectory(
            self, "Куда сохранить результат", self._settings.last_dir
        )
        if not dest:
            return
        self._settings.last_dir = dest
        self._settings.save()
        self._last_saved_dir = Path(dest)
        worker = SaveWorker(entries, Path(dest), self)
        worker.progress.connect(lambda done, total: self._info.setText(f"Сохранение… {done} / {total}"))
        worker.conflict.connect(self._on_conflict)
        worker.finishedSave.connect(self._on_save_finished)
        self._save_worker = worker
        self._info.setText("Сохранение…")
        worker.start()
        self._refresh_state()

    def _on_conflict(self, path: str, is_folder: bool) -> None:
        dialog = ConflictDialog(Path(path), is_folder, self)
        dialog.exec()
        if self._save_worker is not None:
            self._save_worker.answer(dialog.action, dialog.apply_to_all)

    def _on_save_finished(self, report: SaveReport) -> None:
        worker, self._save_worker = self._save_worker, None
        if worker is not None:
            worker.wait()
            worker.deleteLater()
        extra = []
        if report.renamed:
            extra.append(f"переименовано: {report.renamed}")
        if report.skipped:
            extra.append(f"пропущено: {report.skipped}")
        if report.errors:
            extra.append(f"ошибок: {len(report.errors)}")
        text = f"Сохранено файлов: {report.saved} → {self._last_saved_dir}"
        if extra:
            text += f" ({', '.join(extra)})"
        self._summary_text = text
        self._refresh_state()
        box = QMessageBox(self)
        box.setWindowTitle("Сохранение завершено")
        box.setIcon(QMessageBox.Icon.Warning if report.errors else QMessageBox.Icon.Information)
        box.setText(text)
        if report.errors:
            box.setDetailedText("\n".join(f"{p}: {e}" for p, e in report.errors))
        open_button = box.addButton("Открыть папку", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Закрыть", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is open_button:
            self.open_saved_folder()

    def open_saved_folder(self) -> None:
        if self._last_saved_dir is not None and self._last_saved_dir.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._last_saved_dir)))

    def export_log(self) -> None:
        results = self._model.results()
        if not results or self._last_options is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Экспорт лога", str(Path(self._settings.last_dir or ".") / "imgforge-log.txt"),
            "Текстовый файл (*.txt)",
        )
        if not path:
            return
        try:
            Path(path).write_text(format_log(results, self._last_options, self._last_elapsed), encoding="utf-8")
        except OSError as exc:
            QMessageBox.warning(self, "Экспорт лога", f"Не удалось записать файл:\n{exc}")

    # ================================================================== compare / context menu

    def _selected_rows(self) -> list[int]:
        return sorted(i.row() for i in self._table.selectionModel().selectedRows())

    def _selected_result(self) -> FileResult | None:
        rows = self._selected_rows()
        if not rows:
            return None
        result = self._model.result(rows[0])
        return result if result is not None and result.ok else None

    def _compare_selected(self) -> None:
        result = self._selected_result()
        if result is not None:
            self._open_compare(result)

    def _on_double_click(self, index: QModelIndex) -> None:
        result = self._model.result(index.row())
        if result is None:
            return
        if result.ok:
            self._open_compare(result)
        else:
            QMessageBox.warning(self, result.source.name, f"{result.source.path}\n\n{result.message}")

    def _open_compare(self, result: FileResult) -> None:
        dialog = CompareDialog(result, self._theme.tokens, self)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self._compare_dialogs.append(dialog)
        dialog.destroyed.connect(lambda *_: self._compare_dialogs.remove(dialog) if dialog in self._compare_dialogs else None)
        dialog.show()

    def _context_menu(self, pos: QPoint) -> None:
        index = self._table.indexAt(pos)
        if not index.isValid():
            return
        if not self._table.selectionModel().isRowSelected(index.row(), QModelIndex()):
            self._table.selectRow(index.row())
        menu = QMenu(self)
        result = self._model.result(index.row())
        compare = menu.addAction("Сравнить до/после")
        compare.setEnabled(result is not None and result.ok)
        show = menu.addAction("Показать оригинал в папке")
        remove = menu.addAction("Удалить из очереди")
        remove.setEnabled(not (self.running or self.saving))
        chosen = menu.exec(self._table.viewport().mapToGlobal(pos))
        if chosen is compare and result is not None:
            self._open_compare(result)
        elif chosen is show:
            subprocess.Popen(["explorer", "/select,", str(self._model.item(index.row()).path)])
        elif chosen is remove:
            self.remove_selected()

    # ================================================================== lifecycle

    def _cleanup_work_dir(self, wait: bool = False) -> None:
        work_dir, self._work_dir = self._work_dir, None
        if work_dir is None:
            return
        if wait:
            shutil.rmtree(work_dir, ignore_errors=True)
        else:
            threading.Thread(target=shutil.rmtree, args=(work_dir, True), daemon=True).start()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        if self.running:
            answer = QMessageBox.question(
                self, "ImgForge", "Обработка ещё идёт. Отменить и выйти?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            assert self._process_worker is not None
            self._process_worker.cancel()
            self._process_worker.wait()
        if self._save_worker is not None:
            self._save_worker.cancel()
            self._save_worker.wait()
        if self._scan_worker is not None:
            self._scan_worker.requestInterruption()
            self._scan_worker.wait()
        for dialog in list(self._compare_dialogs):
            dialog.close()
        self._settings.geometry = self.saveGeometry()
        self._settings.save()
        self._cleanup_work_dir(wait=True)
        super().closeEvent(event)
