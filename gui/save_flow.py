"""Saving processed files: destination dialog, worker, name conflicts and the final report."""
from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFileDialog, QMessageBox, QWidget

from core.saver import SaveEntry, SaveReport
from gui.formatting import save_report_text
from gui.settings import AppSettings
from gui.widgets.conflict_dialog import ConflictDialog
from gui.workers import SaveWorker


class SaveFlow(QObject):
    """Everything between the "Сохранить…" button and the "Сохранение завершено" box."""

    started = Signal()
    status = Signal(str)  # progress text for the status bar
    finished = Signal(str)  # the summary sentence

    def __init__(self, window: QWidget, settings: AppSettings) -> None:
        super().__init__(window)
        self._window = window
        self._settings = settings
        self._worker: SaveWorker | None = None
        self._dest: Path | None = None

    @property
    def active(self) -> bool:
        return self._worker is not None

    @property
    def dest(self) -> Path | None:
        """The folder of the last save."""
        return self._dest

    def forget_dest(self) -> None:
        self._dest = None

    def start(self, entries: Sequence[SaveEntry]) -> None:
        if self.active or not entries:
            return
        folder = QFileDialog.getExistingDirectory(self._window, "Куда сохранить результат", self._settings.last_dir)
        if not folder:
            return
        self._settings.last_dir = folder
        self._settings.save()
        self._dest = Path(folder)
        worker = SaveWorker(entries, self._dest, self)
        worker.progress.connect(lambda done, total: self.status.emit(f"Сохранение… {done} / {total}"))
        worker.conflict.connect(self._on_conflict)
        worker.finishedSave.connect(self._on_finished)
        self._worker = worker
        self.status.emit("Сохранение…")
        worker.start()
        self.started.emit()

    def cancel_and_wait(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
            self._worker.wait()

    def open_dest(self) -> None:
        if self._dest is not None and self._dest.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._dest)))

    def _on_conflict(self, path: str, is_folder: bool) -> None:
        dialog = ConflictDialog(Path(path), is_folder, self._window)
        dialog.exec()
        if self._worker is not None:
            self._worker.answer(dialog.action, dialog.apply_to_all)

    def _on_finished(self, report: SaveReport) -> None:
        worker, self._worker = self._worker, None
        if worker is not None:
            worker.wait()
            worker.deleteLater()
        text = save_report_text(report, self._dest)
        self.finished.emit(text)
        box = QMessageBox(self._window)
        box.setWindowTitle("Сохранение завершено")
        box.setIcon(QMessageBox.Icon.Warning if report.errors else QMessageBox.Icon.Information)
        box.setText(text)
        if report.errors:
            box.setDetailedText("\n".join(f"{p}: {e}" for p, e in report.errors))
        open_button = box.addButton("Открыть папку", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Закрыть", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is open_button:
            self.open_dest()
