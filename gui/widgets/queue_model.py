"""Table model for the queue and the results (one virtualized table for both)."""
from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QPersistentModelIndex, Qt
from PySide6.QtGui import QColor

from core.formats import format_info
from core.models import STATUS_LABELS, FileResult, SourceItem, Status
from core.utils import format_size
from gui.themes.tokens import Tokens
from gui.widgets.thumbnails import ThumbnailCache

COLUMNS = ("", "Файл", "Папка", "Формат", "Размер", "Новый размер", "Экономия", "Статус")
COL_PREVIEW, COL_NAME, COL_FOLDER, COL_FORMAT, COL_SIZE, COL_NEW_SIZE, COL_SAVED, COL_STATUS = range(8)
RESULT_ROLE = Qt.ItemDataRole.UserRole
ITEM_ROLE = Qt.ItemDataRole.UserRole + 1

_Index = QModelIndex | QPersistentModelIndex


class QueueModel(QAbstractTableModel):
    """Rows are queued images; once processed they also carry their :class:`FileResult`."""

    def __init__(self, thumbnails: ThumbnailCache, tokens: Tokens, parent=None) -> None:
        super().__init__(parent)
        self._thumbs = thumbnails
        self._tokens = tokens
        self._items: list[SourceItem] = []
        self._results: list[FileResult | None] = []
        thumbnails.ready.connect(self._thumbnails_ready)

    # -- model API ----------------------------------------------------------------

    def rowCount(self, parent: _Index = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self._items)

    def columnCount(self, parent: _Index = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(COLUMNS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return COLUMNS[section]
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.TextAlignmentRole:
            right = section in (COL_SIZE, COL_NEW_SIZE, COL_SAVED)
            return int((Qt.AlignmentFlag.AlignRight if right else Qt.AlignmentFlag.AlignLeft) | Qt.AlignmentFlag.AlignVCenter)
        return None

    def data(self, index: _Index, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row, col = index.row(), index.column()
        item, result = self._items[row], self._results[row]

        if role == Qt.ItemDataRole.DecorationRole and col == COL_PREVIEW:
            return self._thumbs.pixmap(str(item.path))
        if role == RESULT_ROLE:
            return result
        if role == ITEM_ROLE:
            return item
        if role == Qt.ItemDataRole.TextAlignmentRole:
            right = col in (COL_SIZE, COL_NEW_SIZE, COL_SAVED)
            return int((Qt.AlignmentFlag.AlignRight if right else Qt.AlignmentFlag.AlignLeft) | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.ForegroundRole:
            return self._foreground(col, result)
        if role == Qt.ItemDataRole.ToolTipRole:
            return self._tooltip(item, result)
        if role == Qt.ItemDataRole.DisplayRole:
            return self._text(col, item, result)
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

    def clear(self) -> None:
        self.beginResetModel()
        self._items.clear()
        self._results.clear()
        self._thumbs.clear()
        self.endResetModel()

    # -- results ------------------------------------------------------------------------

    def set_result(self, row: int, result: FileResult) -> None:
        if 0 <= row < len(self._results):
            self._results[row] = result
            self.dataChanged.emit(self.index(row, 0), self.index(row, len(COLUMNS) - 1))

    def clear_results(self) -> None:
        if not self._items:
            return
        self._results = [None] * len(self._items)
        self.dataChanged.emit(self.index(0, 0), self.index(len(self._items) - 1, len(COLUMNS) - 1))

    def set_tokens(self, tokens: Tokens) -> None:
        self._tokens = tokens
        if self._items:
            self.dataChanged.emit(
                self.index(0, 0), self.index(len(self._items) - 1, len(COLUMNS) - 1),
                [Qt.ItemDataRole.ForegroundRole],
            )

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

    # -- helpers --------------------------------------------------------------------------------

    def _thumbnails_ready(self) -> None:
        if self._items:
            self.dataChanged.emit(
                self.index(0, COL_PREVIEW), self.index(len(self._items) - 1, COL_PREVIEW),
                [Qt.ItemDataRole.DecorationRole],
            )

    @staticmethod
    def _text(col: int, item: SourceItem, result: FileResult | None) -> str:
        if col == COL_NAME:
            return item.name
        if col == COL_FOLDER:
            return item.folder or "—"
        if col == COL_FORMAT:
            label = format_info(item.format).label
            if result is not None and result.ok and result.output_format not in (None, item.format):
                return f"{label} → {format_info(result.output_format).label}"
            return label
        if col == COL_SIZE:
            return format_size(item.size)
        if result is None:
            return "В очереди" if col == COL_STATUS else ""
        if col == COL_NEW_SIZE:
            return format_size(result.new_size) if result.ok else ""
        if col == COL_SAVED:
            if not result.ok:
                return ""
            pct = result.saved_percent
            return f"{pct:.1f}%" if pct >= 0 else f"−{abs(pct):.1f}%"
        if col == COL_STATUS:
            label = STATUS_LABELS[result.status]
            if result.status is Status.ERROR:
                return f"{label}: {result.message}"
            return f"{label} ⚠" if result.warnings else label
        return ""

    def _foreground(self, col: int, result: FileResult | None):
        t = self._tokens
        if col in (COL_FOLDER,) or (col == COL_STATUS and result is None):
            return QColor(t.muted)
        if result is None:
            return None
        if col == COL_STATUS:
            if result.status is Status.ERROR:
                return QColor(t.danger)
            if result.status is Status.ALREADY_OPTIMIZED:
                return QColor(t.muted)
            return QColor(t.warning if result.warnings else t.success)
        if col == COL_SAVED and result.ok:
            return QColor(t.success if result.saved_percent > 0 else t.warning)
        return None

    @staticmethod
    def _tooltip(item: SourceItem, result: FileResult | None) -> str:
        lines = [str(item.path)]
        if result is not None:
            if result.message:
                lines.append(result.message)
            lines.extend(w for w in result.warnings if w != result.message)
        return "\n".join(lines)
