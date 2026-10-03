"""Background threads: nothing heavy ever runs on the GUI thread."""
from __future__ import annotations

import threading
from collections.abc import Sequence
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from core.models import SourceItem
from core.options import ProcessingOptions
from core.pipeline import BatchRunner
from core.preview import load_display_image
from core.saver import ConflictAction, SaveEntry, save_outputs
from core.scanner import scan_paths
from gui.imaging import pil_to_qimage


class ScanWorker(QThread):
    """Recursively scans dropped files/folders."""

    progress = Signal(int)
    done = Signal(object)  # ScanResult

    def __init__(self, paths: Sequence[Path], known: Sequence[Path], parent=None) -> None:
        super().__init__(parent)
        self._paths = list(paths)
        self._known = list(known)

    def run(self) -> None:
        result = scan_paths(
            self._paths,
            known=self._known,
            progress=self.progress.emit,
            cancelled=self.isInterruptionRequested,
        )
        self.done.emit(result)


class ProcessWorker(QThread):
    """Runs a :class:`BatchRunner` (a pool of worker processes) off the GUI thread."""

    resultReady = Signal(object)  # FileResult
    finishedAll = Signal(object)  # BatchOutcome
    failed = Signal(str)

    def __init__(
        self,
        items: Sequence[SourceItem],
        options: ProcessingOptions,
        work_dir: Path,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._cancel = threading.Event()
        self._runner = BatchRunner(items, options, work_dir, self.resultReady.emit, self._cancel)

    def cancel(self) -> None:
        """Stop submitting new files; running ones finish and are kept."""
        self._cancel.set()

    def run(self) -> None:
        try:
            self.finishedAll.emit(self._runner.run())
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class SaveWorker(QThread):
    """Copies processed files to the destination, asking the GUI about name conflicts."""

    progress = Signal(int, int)
    conflict = Signal(str, bool)  # existing path, is_folder
    finishedSave = Signal(object)  # SaveReport

    def __init__(self, entries: Sequence[SaveEntry], dest: Path, parent=None) -> None:
        super().__init__(parent)
        self._entries = list(entries)
        self._dest = dest
        self._cancel = threading.Event()
        self._answered = threading.Event()
        self._answer: tuple[ConflictAction, bool] = (ConflictAction.SKIP, False)
        self._sticky: dict[bool, ConflictAction] = {}

    def cancel(self) -> None:
        self._cancel.set()
        self._answered.set()

    def answer(self, action: ConflictAction, apply_to_all: bool) -> None:
        """Called from the GUI thread with the user's decision."""
        self._answer = (action, apply_to_all)
        self._answered.set()

    def _resolve(self, path: Path, is_folder: bool) -> ConflictAction:
        if is_folder in self._sticky:
            return self._sticky[is_folder]
        self._answered.clear()
        self.conflict.emit(str(path), is_folder)
        self._answered.wait()
        if self._cancel.is_set():
            return ConflictAction.SKIP
        action, apply_to_all = self._answer
        if apply_to_all:
            self._sticky[is_folder] = action
        return action

    def run(self) -> None:
        report = save_outputs(
            self._entries,
            self._dest,
            self._resolve,
            progress=self.progress.emit,
            cancelled=self._cancel.is_set,
        )
        self.finishedSave.emit(report)


class ImageLoadWorker(QThread):
    """Loads the original and the processed image for the before/after view."""

    loaded = Signal(object, object)  # QImage original, QImage result
    failed = Signal(str)

    def __init__(self, original: Path, result: Path, parent=None) -> None:
        super().__init__(parent)
        self._original = original
        self._result = result

    def run(self) -> None:
        try:
            original = pil_to_qimage(load_display_image(self._original))
            result = pil_to_qimage(load_display_image(self._result))
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(f"{type(exc).__name__}: {exc}")
            return
        self.loaded.emit(original, result)
