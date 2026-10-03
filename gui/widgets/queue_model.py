"""Table model for the queue and the results (one virtualized list for both)."""
from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QPersistentModelIndex, Qt
from PySide6.QtGui import QPixmap

from core.formats import ImageFormat
from core.models import FileResult, SourceItem, Status
from core.options import ProcessingOptions
from gui.widgets.thumbnails import ThumbnailCache

RESULT_ROLE = Qt.ItemDataRole.UserRole
ITEM_ROLE = Qt.ItemDataRole.UserRole + 1
STATE_ROLE = Qt.ItemDataRole.UserRole + 2

# Row states shown in the result column.
QUEUED, WAITING, WORKING, DONE, OPTIMIZED, FAILED = "queued", "waiting", "working", "done", "optimized", "failed"

_Index = QModelIndex | QPersistentModelIndex


class QueueModel(QAbstractTableModel):
    """One row per queued image; once processed a row also carries its :class:`FileResult`.

    While a batch runs the first ``workers`` rows without a result are the ones being processed
    (the pipeline submits in queue order), the rest are waiting.
    """

    def __init__(self, thumbnails: ThumbnailCache, parent=None) -> None:
        super().__init__(parent)
        self._thumbs = thumbnails
        self._items: list[SourceItem] = []
        self._results: list[FileResult | None] = []
        self._options: ProcessingOptions | None = None
        self._running = False
        self._slots = 1
        self._cursor = 0  # every row before it already has a result
        self._inflight: set[int] = set()
        self._folders: set[str] | None = None
        thumbnails.ready.connect(self._thumbnails_ready)

    # -- model API ----------------------------------------------------------------

    def rowCount(self, parent: _Index = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self._items)

    def columnCount(self, parent: _Index = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else 1

    def data(self, index: _Index, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = index.row()
        item, result = self._items[row], self._results[row]
        if role == Qt.ItemDataRole.DisplayRole:
            return item.name
        if role == RESULT_ROLE:
            return result
        if role == ITEM_ROLE:
            return item
        if role == STATE_ROLE:
            return self.state(row)
        if role == Qt.ItemDataRole.ToolTipRole:
            return self._tooltip(item, result)
        return None

    # -- queue editing --------------------------------------------------------------

    def add_items(self, items: Iterable[SourceItem]) -> int:
        """Append ``items`` and return how many were added."""
        new = list(items)
        if not new:
            return 0
        first = len(self._items)
        self.beginInsertRows(QModelIndex(), first, first + len(new) - 1)
        self._items.extend(new)
        self._results.extend([None] * len(new))
        self.endInsertRows()
        self._folders = None
        return len(new)

    def remove_rows(self, rows: Iterable[int]) -> None:
        """Remove the given rows (contiguous runs are removed in one step)."""
        ordered = sorted(set(rows), reverse=True)
        i = 0
        while i < len(ordered):
            last = ordered[i]
            first = last
            i += 1
            while i < len(ordered) and ordered[i] == first - 1:
                first = ordered[i]
                i += 1
            self.beginRemoveRows(QModelIndex(), first, last)
            for item in self._items[first : last + 1]:
                self._thumbs.forget(str(item.path))
            del self._items[first : last + 1]
            del self._results[first : last + 1]
            self.endRemoveRows()
        self._cursor = 0
        self._folders = None

    def clear(self) -> None:
        self.beginResetModel()
        self._items.clear()
        self._results.clear()
        self._thumbs.clear()
        self._cursor = 0
        self._inflight.clear()
        self._folders = None
        self.endResetModel()

    # -- results ------------------------------------------------------------------------

    def set_result(self, row: int, result: FileResult) -> None:
        if 0 <= row < len(self._results):
            self._results[row] = result
            self._track_inflight()
            self.dataChanged.emit(self.index(row, 0), self.index(row, 0))

    def clear_results(self) -> None:
        if not self._items:
            return
        self._results = [None] * len(self._items)
        self._cursor = 0
        self._inflight.clear()
        self._emit_all()

    def set_running(self, running: bool, slots: int = 1) -> None:
        """Tell the model whether a batch is in progress and how many files run at once."""
        self._running, self._slots = running, max(1, slots)
        self._track_inflight()
        self._emit_all()

    def set_options(self, options: ProcessingOptions) -> None:
        """The options the next run will use (decide the target format shown in each row)."""
        self._options = options
        self._emit_all()

    # -- accessors ------------------------------------------------------------------------

    def items(self) -> list[SourceItem]:
        return list(self._items)

    def item(self, row: int) -> SourceItem:
        return self._items[row]

    def result(self, row: int) -> FileResult | None:
        return self._results[row]

    def results(self) -> list[FileResult]:
        """All available results in queue order."""
        return [r for r in self._results if r is not None]

    def total_source_size(self) -> int:
        return sum(i.size for i in self._items)

    def folder_count(self) -> int:
        """Number of distinct folders the queued files came from (loose files count as none)."""
        if self._folders is None:
            self._folders = {i.folder for i in self._items if i.folder}
        return len(self._folders)

    def thumbnail(self, row: int) -> QPixmap | None:
        return self._thumbs.pixmap(str(self._items[row].path))

    def state(self, row: int) -> str:
        result = self._results[row]
        if result is not None:
            if result.status is Status.ERROR:
                return FAILED
            return OPTIMIZED if result.status is Status.ALREADY_OPTIMIZED else DONE
        if self._running:
            return WORKING if row in self._inflight else WAITING
        return QUEUED

    def target_format(self, row: int) -> ImageFormat:
        """Output format of a row: the real one when processed, otherwise predicted from the options."""
        result = self._results[row]
        if result is not None and result.output_format is not None:
            return result.output_format
        item = self._items[row]
        return self._options.output_format_for(item.format) if self._options else item.format

    # -- helpers --------------------------------------------------------------------------------

    def _track_inflight(self) -> None:
        self._inflight.clear()
        if not self._running:
            return
        n, i = len(self._items), self._cursor
        while i < n and self._results[i] is not None:
            i += 1
        self._cursor = i
        found = 0
        while i < n and found < self._slots:
            if self._results[i] is None:
                self._inflight.add(i)
                found += 1
            i += 1

    def _emit_all(self) -> None:
        if self._items:
            self.dataChanged.emit(self.index(0, 0), self.index(len(self._items) - 1, 0))

    def _thumbnails_ready(self) -> None:
        self._emit_all()

    @staticmethod
    def _tooltip(item: SourceItem, result: FileResult | None) -> str:
        lines = [str(item.path)]
        if result is not None:
            if result.message:
                lines.append(result.message)
            lines.extend(w for w in result.warnings if w != result.message)
        return "\n".join(lines)
