"""The main application window."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from PySide6.QtCore import QModelIndex, QPoint, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QCloseEvent,
    QDesktopServices,
    QDragEnterEvent,
    QDragLeaveEvent,
    QDropEvent,
    QIcon,
    QKeySequence,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QTableView,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core.formats import INPUT_EXTENSIONS
from core.models import FileResult, summarize
from core.options import ProcessingOptions
from core.pipeline import BatchOutcome
from core.report import format_log
from core.saver import SaveEntry, SaveReport
from core.scanner import ScanResult
from core.utils import format_duration, format_size
from gui.compare_view import CompareDialog
from gui.settings import AppSettings
from gui.themes.manager import DARK_THEME, LIGHT_THEME, SYSTEM, ThemeManager
from gui.widgets.conflict_dialog import ConflictDialog
from gui.widgets.drop_zone import DropZone
from gui.widgets.queue_model import (
    COL_FOLDER,
    COL_FORMAT,
    COL_NAME,
    COL_NEW_SIZE,
    COL_PREVIEW,
    COL_SAVED,
    COL_SIZE,
    QueueModel,
)
from gui.widgets.settings_panel import SettingsPanel
from gui.widgets.thumbnails import ThumbnailCache
from gui.workers import ProcessWorker, SaveWorker, ScanWorker

THUMB_SIZE = 56


def _file_filter() -> str:
    patterns = " ".join(f"*{ext}" for ext in sorted(INPUT_EXTENSIONS))
    return f"Изображения ({patterns});;Все файлы (*.*)"


class MainWindow(QMainWindow):
    """Queue, settings, progress, results and the save/compare actions."""

    def __init__(self, theme: ThemeManager, settings: AppSettings, icon: QIcon | None = None) -> None:
        super().__init__()
        self._theme = theme
        self._settings = settings
        self.setWindowTitle("ImgForge")
        if icon is not None:
            self.setWindowIcon(icon)
        self.setAcceptDrops(True)
        self.setMinimumSize(1100, 700)
        self.resize(1240, 800)
        if settings.geometry is not None:
            self.restoreGeometry(settings.geometry)

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
        self._cancelled = False
        self._done = 0
        self._total = 0
        self._bytes_done = 0
        self._bytes_total = 0
        self._started_at = 0.0
        self._compare_dialogs: list[CompareDialog] = []

        self._thumbs = ThumbnailCache(THUMB_SIZE, parent=self)
        self._model = QueueModel(self._thumbs, theme.tokens, self)

        self._build_ui()
        self._build_actions()
        self._timer = QTimer(self)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self._tick)
        theme.changed.connect(self._on_theme_changed)
        self._refresh_state()

    # ================================================================== construction

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)

        brand = QLabel("ImgForge")
        brand.setObjectName("brand")
        self._btn_add_files = QPushButton("Добавить файлы")
        self._btn_add_folder = QPushButton("Добавить папку")
        self._btn_clear = QPushButton("Очистить")
        self._theme_button = QToolButton()
        self._theme_button.setText("Тема")
        self._theme_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._theme_button.setMenu(self._build_theme_menu())

        top = QHBoxLayout()
        top.addWidget(brand)
        top.addSpacing(16)
        top.addWidget(self._btn_add_files)
        top.addWidget(self._btn_add_folder)
        top.addWidget(self._btn_clear)
        top.addStretch()
        top.addWidget(self._theme_button)

        # Queue / results table
        self._table = QTableView()
        self._table.setModel(self._model)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self._table.setAlternatingRowColors(True)
        self._table.setShowGrid(False)
        self._table.setWordWrap(False)
        self._table.setIconSize(QSize(THUMB_SIZE, THUMB_SIZE))
        self._table.verticalHeader().setVisible(False)
        self._table.verticalHeader().setDefaultSectionSize(THUMB_SIZE + 10)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        header = self._table.horizontalHeader()
        header.setHighlightSections(False)
        header.setStretchLastSection(True)  # the status column takes the remaining width
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        for col, width in (
            (COL_PREVIEW, THUMB_SIZE + 12), (COL_NAME, 170), (COL_FOLDER, 130), (COL_FORMAT, 104),
            (COL_SIZE, 80), (COL_NEW_SIZE, 100), (COL_SAVED, 80),
        ):
            self._table.setColumnWidth(col, width)
        header.setSectionResizeMode(COL_PREVIEW, QHeaderView.ResizeMode.Fixed)

        self._drop_zone = DropZone(self._theme.tokens)
        self._stack = QStackedWidget()
        self._stack.addWidget(self._drop_zone)
        self._stack.addWidget(self._table)

        self._panel = SettingsPanel(self._settings)

        body = QHBoxLayout()
        body.setSpacing(14)
        body.addWidget(self._stack, 1)
        body.addWidget(self._panel, 0, Qt.AlignmentFlag.AlignTop)

        # Bottom area
        self._info = QLabel()
        self._info.setObjectName("summary")
        self._info.setWordWrap(True)
        self._progress = QProgressBar()
        self._progress.setTextVisible(True)
        self._progress_text = QLabel()
        self._progress_text.setProperty("muted", True)
        self._progress_text.setMinimumWidth(300)
        self._progress_text.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self._btn_start = QPushButton("Начать")
        self._btn_start.setObjectName("primary")
        self._btn_cancel = QPushButton("Отмена")
        self._btn_cancel.setObjectName("danger")
        self._btn_compare = QPushButton("Сравнить")
        self._btn_save = QPushButton("Сохранить…")
        self._btn_save.setObjectName("primary")
        self._btn_open = QPushButton("Открыть папку")
        self._btn_log = QPushButton("Экспорт лога")

        progress_row = QHBoxLayout()
        progress_row.addWidget(self._progress, 1)
        progress_row.addWidget(self._progress_text)
        actions = QHBoxLayout()
        actions.addWidget(self._btn_start)
        actions.addWidget(self._btn_cancel)
        actions.addWidget(self._btn_compare)
        actions.addStretch()
        actions.addWidget(self._btn_log)
        actions.addWidget(self._btn_open)
        actions.addWidget(self._btn_save)

        bottom = QFrame()
        bottom.setObjectName("card")
        bottom_layout = QVBoxLayout(bottom)
        bottom_layout.setContentsMargins(16, 12, 16, 12)
        bottom_layout.addWidget(self._info)
        bottom_layout.addLayout(progress_row)
        bottom_layout.addLayout(actions)

        layout = QVBoxLayout(root)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(12)
        layout.addLayout(top)
        layout.addLayout(body, 1)
        layout.addWidget(bottom)

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
        self._table.doubleClicked.connect(self._on_double_click)
        self._table.customContextMenuRequested.connect(self._context_menu)
        self._table.selectionModel().selectionChanged.connect(lambda *_: self._refresh_state())
        self._panel.changed.connect(self._on_settings_changed)

    def _build_theme_menu(self) -> QMenu:
        menu = QMenu(self)
        group = QActionGroup(menu)
        group.setExclusive(True)
        for key, label in ((SYSTEM, "Как в Windows"), (LIGHT_THEME, "Светлая"), (DARK_THEME, "Тёмная")):
            action = QAction(label, menu, checkable=True)
            action.setChecked(self._theme.preference == key)
            action.triggered.connect(lambda _=False, k=key: self._set_theme(k))
            group.addAction(action)
            menu.addAction(action)
        return menu

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
        self._btn_cancel.setVisible(self.running)
        self._btn_save.setEnabled(has_results and not busy)
        self._btn_log.setEnabled(bool(results) and not busy)
        self._btn_open.setEnabled(self._last_saved_dir is not None and self._last_saved_dir.exists())
        self._btn_clear.setEnabled(has_items and not busy)
        self._btn_add_files.setEnabled(not self.running)
        self._btn_add_folder.setEnabled(not self.running)
        self._drop_zone.setEnabled(not self.running)
        self._panel.set_locked(self.running)
        self._btn_compare.setEnabled(self._selected_result() is not None)
        self._progress.setVisible(self.running or self._total > 0)
        self._update_info()

    def _update_info(self) -> None:
        if self.running:
            return
        if self._scan_worker is not None:
            return
        parts: list[str] = []
        if self._summary_text:
            parts.append(self._summary_text)
        else:
            n = self._model.rowCount()
            if n:
                parts.append(f"В очереди: {n} · {format_size(self._model.total_source_size())}")
            else:
                parts.append("Очередь пуста")
        if self._skipped:
            parts.append(f"пропущено не-изображений: {self._skipped}")
        if self._duplicates:
            parts.append(f"уже в очереди: {self._duplicates}")
        self._info.setText(" · ".join(parts))

    def _on_theme_changed(self, tokens) -> None:
        self._model.set_tokens(tokens)
        self._drop_zone.set_tokens(tokens)
        for dialog in self._compare_dialogs:
            dialog.set_tokens(tokens)

    def _set_theme(self, key: str) -> None:
        self._settings.theme = key
        self._theme.set_preference(key)
        self._settings.save()

    def _on_settings_changed(self) -> None:
        self._settings.update_from(self._panel.options())
        self._settings.save()

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
        self._total = self._done = 0
        self._last_saved_dir = None
        self._refresh_state()

    def remove_selected(self) -> None:
        if self.running or self.saving:
            return
        rows = [i.row() for i in self._table.selectionModel().selectedRows()]
        if rows:
            self._model.remove_rows(rows)
            self._summary_text = ""
            self._refresh_state()

    # ----- drag & drop

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if not self.running and event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._drop_zone.set_highlighted(True)
        else:
            event.ignore()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:  # noqa: N802
        self._drop_zone.set_highlighted(False)

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        self._drop_zone.set_highlighted(False)
        paths = [Path(u.toLocalFile()) for u in event.mimeData().urls() if u.isLocalFile()]
        if paths:
            event.acceptProposedAction()
            self.add_paths(paths)

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
        self._cancelled = False
        self._total, self._done = len(items), 0
        self._bytes_total = sum(i.size for i in items) or 1
        self._bytes_done = 0
        self._started_at = time.monotonic()
        self._progress.setRange(0, self._total)
        self._progress.setValue(0)
        worker = ProcessWorker(items, options, self._work_dir, self)
        worker.resultReady.connect(self._on_result)
        worker.finishedAll.connect(self._on_process_finished)
        worker.failed.connect(self._on_process_failed)
        self._process_worker = worker
        self._info.setText(f"Обработка: {self._total} файлов, потоков: {options.workers}")
        self._timer.start()
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
        self._progress.setValue(self._done)

    def _tick(self) -> None:
        if not self.running:
            return
        elapsed = time.monotonic() - self._started_at
        fraction = self._bytes_done / self._bytes_total
        text = f"{self._done} / {self._total} · прошло {format_duration(elapsed)}"
        if fraction >= 0.02 and self._done < self._total:
            text += f" · осталось ~{format_duration(elapsed * (1 - fraction) / fraction)}"
        self._progress_text.setText(text)

    def _on_process_finished(self, outcome: BatchOutcome) -> None:
        self._finish_worker()
        self._last_elapsed = outcome.elapsed
        s = summarize(outcome.results)
        head = (
            f"Отменено: обработано {s.total} из {self._total}"
            if outcome.cancelled
            else f"Готово: {s.total} файлов"
        )
        self._summary_text = (
            f"{head} (OK: {s.ok}, уже оптимизировано: {s.already_optimized}, ошибок: {s.errors}) · "
            f"{format_size(s.size_before)} → {format_size(s.size_after)} · "
            f"сэкономлено {format_size(s.saved_bytes)} ({s.saved_percent:.1f}%)"
        )
        self._progress_text.setText(f"{s.total} / {self._total} · {format_duration(outcome.elapsed)}")
        self._refresh_state()

    def _on_process_failed(self, message: str) -> None:
        self._finish_worker()
        self._summary_text = f"Обработка прервана: {message}"
        self._refresh_state()

    def _finish_worker(self) -> None:
        worker, self._process_worker = self._process_worker, None
        self._timer.stop()
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
