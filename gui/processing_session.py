"""One processing run: the worker, its temp folder, progress counters and the UI timers."""
from __future__ import annotations

import shutil
import tempfile
import threading
import time
from collections.abc import Sequence
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

from core.models import FileResult, SourceItem
from core.options import ProcessingOptions
from core.pipeline import BatchOutcome
from core.utils import format_duration
from gui.workers import ProcessWorker


class ProcessingSession(QObject):
    """Owns everything about a batch run; the window only reacts to its signals."""

    resultReady = Signal(object)  # FileResult
    progress = Signal(int, int, int, str)  # done, total, in flight, meta text
    animationTick = Signal()
    finished = Signal(object)  # BatchOutcome
    failed = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._worker: ProcessWorker | None = None
        self._work_dir: Path | None = None
        self._options: ProcessingOptions | None = None
        self._done = self._total = 0
        self._bytes_done = 0
        self._bytes_total = 1
        self._started_at = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self._emit_progress)
        self._anim = QTimer(self)
        self._anim.setInterval(90)
        self._anim.timeout.connect(self.animationTick)

    # ---- state
    @property
    def running(self) -> bool:
        return self._worker is not None

    @property
    def done(self) -> int:
        return self._done

    @property
    def total(self) -> int:
        return self._total

    @property
    def options(self) -> ProcessingOptions | None:
        """The options of the last started run."""
        return self._options

    @property
    def percent(self) -> int:
        return 100 * self._done // self._total if self._total else 0

    def busy_threads(self, options: ProcessingOptions) -> int:
        return max(1, min(options.workers, self._total - self._done))

    # ---- control
    def start(self, items: Sequence[SourceItem], options: ProcessingOptions) -> None:
        self.discard_outputs()
        self._work_dir = Path(tempfile.mkdtemp(prefix="imgforge_"))
        self._options = options
        self._total, self._done = len(items), 0
        self._bytes_total = sum(i.size for i in items) or 1
        self._bytes_done = 0
        self._started_at = time.monotonic()
        worker = ProcessWorker(items, options, self._work_dir, self)
        worker.resultReady.connect(self._on_result)
        worker.finishedAll.connect(self._on_finished)
        worker.failed.connect(self._on_failed)
        self._worker = worker
        self._timer.start()
        self._anim.start()
        self._emit_progress()
        worker.start()

    def cancel(self) -> None:
        if self._worker is not None:
            self._worker.cancel()

    def stop_and_wait(self) -> None:
        """Cancel and block until the worker is gone (window closing)."""
        if self._worker is not None:
            self._worker.cancel()
            self._worker.wait()

    def reset(self) -> None:
        """Forget the last run (the queue was cleared)."""
        self.discard_outputs()
        self._total = self._done = 0

    def discard_outputs(self, wait: bool = False) -> None:
        """Delete the temp folder with the processed files."""
        work_dir, self._work_dir = self._work_dir, None
        if work_dir is None:
            return
        if wait:
            shutil.rmtree(work_dir, ignore_errors=True)
        else:
            threading.Thread(target=shutil.rmtree, args=(work_dir, True), daemon=True).start()

    # ---- worker callbacks
    def _on_result(self, result: FileResult) -> None:
        self._done += 1
        self._bytes_done += result.source.size
        self._emit_progress()
        self.resultReady.emit(result)

    def _emit_progress(self) -> None:
        if self._worker is None:
            return
        options = self._options
        workers = options.workers if options else 0
        elapsed = time.monotonic() - self._started_at
        fraction = self._bytes_done / self._bytes_total
        threads = self.busy_threads(options) if options else 0
        meta = f"THR {threads}/{workers} · {format_duration(elapsed)}"
        if fraction >= 0.02 and self._done < self._total:
            meta += f" · ETA {format_duration(elapsed * (1 - fraction) / fraction)}"
        inflight = min(options.workers if options else 1, self._total - self._done)
        self.progress.emit(self._done, self._total, inflight, meta)

    def _release_worker(self) -> None:
        worker, self._worker = self._worker, None
        self._timer.stop()
        self._anim.stop()
        if worker is not None:
            worker.wait()
            worker.deleteLater()

    def _on_finished(self, outcome: BatchOutcome) -> None:
        self._release_worker()
        self.finished.emit(outcome)

    def _on_failed(self, message: str) -> None:
        self._release_worker()
        self.failed.emit(message)
