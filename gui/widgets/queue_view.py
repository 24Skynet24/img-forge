"""The queue / results list: column header, row delegate and the view with its ✕ buttons."""
from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QModelIndex, QPoint, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QFontMetrics, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QStyle,
    QStyledItemDelegate,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from core.formats import format_info
from core.models import FileResult
from core.utils import format_size
from gui.themes.fonts import font
from gui.widgets.kit import col, draw_frame, hatch_brush
from gui.widgets.queue_model import (
    DONE,
    FAILED,
    OPTIMIZED,
    QUEUED,
    RESULT_ROLE,
    STATE_ROLE,
    WAITING,
    WORKING,
    QueueModel,
)

ROW_HEIGHT = 46
PAD, GAP = 16, 10
# idx, thumbnail, file (flexible), format, source size, result, action
_COLUMNS = (30, 36, None, 112, 72, 150, 28)
IDX, THUMB, FILE, FORMAT, SIZE, RESULT, ACTION = range(7)
_V = int(Qt.AlignmentFlag.AlignVCenter)


@lru_cache(maxsize=4096)
def _elide(px: int, weight: int, text: str, mode: Qt.TextElideMode, width: int) -> str:
    """Elided text, cached: rows are repainted on every resize step with the same strings."""
    return QFontMetrics(font(px, weight)).elidedText(text, mode, width)


@lru_cache(maxsize=1024)
def _advance(px: int, weight: int, text: str) -> int:
    return QFontMetrics(font(px, weight)).horizontalAdvance(text)


def column_spans(width: int) -> list[tuple[int, int]]:
    """``(x, width)`` of every column for a row of ``width`` px (shared by header and rows)."""
    fixed = sum(w for w in _COLUMNS if w) + GAP * (len(_COLUMNS) - 1) + 2 * PAD
    flexible = max(40, width - fixed)
    spans, x = [], PAD
    for w in _COLUMNS:
        w = w or flexible
        spans.append((x, w))
        x += w + GAP
    return spans


def remove_button_rect(row: QRect) -> QRect:
    """The 24 px ✕ button inside a row rectangle."""
    x, w = column_spans(row.width())[ACTION]
    return QRect(row.left() + x + w - 24, row.top() + (row.height() - 24) // 2, 24, 24)


def _chip(p: QPainter, x: int, cy: int, text: str, kind: str) -> int:
    """Draw a small tag at ``x`` (vertically centred on ``cy``); returns its width."""
    f = font(10, 700)
    w, h = _advance(10, 700, text) + 10, QFontMetrics(f).height() + 2
    rect = QRect(x, cy - h // 2, w, h)
    if kind == "lime":
        p.fillRect(rect, col("lime"))
        fg = col("onlime")
    elif kind == "ink":
        p.fillRect(rect, col("ink"))
        fg = col("inv")
    else:
        draw_frame(p, rect, col("ink"))
        fg = col("ink")
    p.setFont(f)
    p.setPen(fg)
    p.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), text)
    return w


class RowDelegate(QStyledItemDelegate):
    """Paints one whole row of the queue (all columns) in the grid shared with the header."""

    def __init__(self, view: QueueView) -> None:
        super().__init__(view)
        self._view = view

    def sizeHint(self, option, index) -> QSize:  # noqa: N802
        return QSize(option.rect.width(), ROW_HEIGHT)

    def paint(self, p: QPainter, option, index: QModelIndex) -> None:
        model: QueueModel = index.model()  # type: ignore[assignment]
        row = index.row()
        rect: QRect = option.rect
        item = model.item(row)
        result: FileResult | None = index.data(RESULT_ROLE)
        state: str = index.data(STATE_ROLE)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)

        p.save()
        p.setClipRect(rect)
        if selected or hovered:
            p.fillRect(rect, col("hover"))
        elif state == FAILED:
            p.fillRect(rect, hatch_brush("line2"))
        if selected:
            p.fillRect(QRect(rect.left(), rect.top(), 3, rect.height()), col("ink"))
        p.fillRect(QRect(rect.left(), rect.bottom(), rect.width(), 1), col("line2"))

        spans = [QRect(rect.left() + x, rect.top(), w, rect.height()) for x, w in column_spans(rect.width())]
        mid = rect.top() + rect.height() // 2

        # idx
        p.setFont(font(11))
        p.setPen(col("mute"))
        p.drawText(spans[IDX], _V, f"{row + 1:03d}")

        # thumbnail
        thumb = QRect(spans[THUMB].left(), mid - 18, 36, 36)
        pixmap = model.thumbnail(row)
        if pixmap is None or pixmap.isNull():
            p.fillRect(thumb, hatch_brush("line2", background="panel"))
        else:
            p.fillRect(thumb, col("panel"))
            target = QSize(pixmap.size() / pixmap.devicePixelRatio()).scaled(34, 34, Qt.AspectRatioMode.KeepAspectRatio)
            box = QRect(0, 0, target.width(), target.height())
            box.moveCenter(thumb.center())
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            p.drawPixmap(box, pixmap)
        draw_frame(p, thumb, col("line"))

        # file name + folder
        name_rect = spans[FILE]
        p.setFont(font(12, 500))
        p.setPen(col("ink"))
        name = _elide(12, 500, item.name, Qt.TextElideMode.ElideRight, name_rect.width())
        p.drawText(QRect(name_rect.left(), mid - 17, name_rect.width(), 17), _V, name)
        p.setFont(font(10))
        p.setPen(col("mute"))
        where = item.folder or str(item.path.parent)
        where = _elide(10, 400, where, Qt.TextElideMode.ElideLeft, name_rect.width())
        p.drawText(QRect(name_rect.left(), mid + 1, name_rect.width(), 14), _V, where)

        # format: SRC → DST
        fmt = spans[FORMAT]
        x = fmt.left()
        src = format_info(item.format).label.upper()
        dst = format_info(model.target_format(row)).label.upper()
        p.setFont(font(11))
        p.setPen(col("mute"))
        p.drawText(QRect(x, rect.top(), 60, rect.height()), _V, src)
        x += _advance(11, 400, src) + 6
        p.setFont(font(11, 700))
        p.setPen(col("vtext"))
        p.drawText(QRect(x, rect.top(), 14, rect.height()), _V, "→")
        x += _advance(11, 700, "→") + 6
        p.setPen(col("ink"))
        p.drawText(QRect(x, rect.top(), fmt.right() - x + 1, rect.height()), _V, dst)

        # source size
        p.setFont(font(11))
        p.setPen(col("ink"))
        p.drawText(spans[SIZE], _V | int(Qt.AlignmentFlag.AlignRight), format_size(item.size))

        self._paint_result(p, spans[RESULT], mid, state, result)
        self._paint_action(p, rect, state, result, row)
        p.restore()

    def _paint_result(self, p: QPainter, cell: QRect, mid: int, state: str, result: FileResult | None) -> None:
        if state == QUEUED:
            p.setFont(font(11, spacing=0.06))
            p.setPen(col("mute"))
            p.drawText(cell, _V, "ГОТОВ К ЗАПУСКУ")
        elif state == WAITING:
            p.setFont(font(11, spacing=0.06))
            p.setPen(col("mute"))
            p.drawText(cell, _V, "ОЖИДАНИЕ…")
        elif state == WORKING:
            label_w = 60
            bar = QRect(cell.left(), mid - 4, cell.width() - label_w, 8)
            p.fillRect(bar.adjusted(1, 1, -1, -1), hatch_brush("violet", offset=self._view.phase))
            draw_frame(p, bar, col("ink"))
            p.setFont(font(10, 700))
            p.setPen(col("ink"))
            p.drawText(QRect(bar.right() + 8, cell.top(), label_w - 8, cell.height()), _V, "РАБОТА")
        elif state in (DONE, OPTIMIZED) and result is not None:
            size_text = format_size(result.new_size)
            p.setFont(font(11, 700))
            p.setPen(col("ink"))
            p.drawText(QRect(cell.left(), cell.top(), cell.width(), cell.height()), _V, size_text)
            x = cell.left() + _advance(11, 700, size_text) + 8
            pct = result.saved_percent
            if state == OPTIMIZED:
                _chip(p, x, mid, "ОПТИМ.", "outline")
            elif pct >= 30:
                _chip(p, x, mid, f"−{pct:.0f}%", "lime")
            else:
                _chip(p, x, mid, f"−{pct:.0f}%" if pct >= 0 else f"+{abs(pct):.0f}%", "outline")
        elif state == FAILED and result is not None:
            w = _chip(p, cell.left(), mid, "ERR_", "ink")
            p.setFont(font(10))
            p.setPen(col("ink"))
            message = _elide(10, 400, result.message, Qt.TextElideMode.ElideRight, cell.width() - w - 8)
            p.drawText(QRect(cell.left() + w + 8, cell.top(), cell.width() - w - 8, cell.height()), _V, message)

    def _paint_action(self, p: QPainter, rect: QRect, state: str, result: FileResult | None, row: int) -> None:
        button = remove_button_rect(rect)
        if state == QUEUED and self._view.removable:
            hot = self._view.hot_row == row
            if hot:
                p.fillRect(button, col("ink"))
            draw_frame(p, button, col("ink") if hot else col("line"))
            p.setFont(font(11))
            p.setPen(col("inv") if hot else col("ink"))
            p.drawText(button, int(Qt.AlignmentFlag.AlignCenter), "✕")
        elif state == FAILED or (result is not None and result.warnings):
            draw_frame(p, button, col("ink") if state == FAILED else col("line"))
            p.setFont(font(12, 700))
            p.setPen(col("ink") if state == FAILED else col("mute"))
            p.drawText(button, int(Qt.AlignmentFlag.AlignCenter), "!")


class QueueView(QTableView):
    """Single-column table: every row is painted by :class:`RowDelegate`."""

    removeRequested = Signal(int)

    def __init__(self, model: QueueModel, parent=None) -> None:
        super().__init__(parent)
        self.setModel(model)
        self.setItemDelegate(RowDelegate(self))
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setShowGrid(False)
        self.setWordWrap(False)
        self.setFrameShape(QTableView.Shape.NoFrame)
        self.setMouseTracking(True)
        self.horizontalHeader().setVisible(False)
        self.horizontalHeader().setStretchLastSection(True)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(ROW_HEIGHT)
        self.verticalHeader().setSectionResizeMode(self.verticalHeader().ResizeMode.Fixed)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.removable = True
        self.hot_row = -1
        self.phase = 0.0

    def set_removable(self, removable: bool) -> None:
        self.removable = removable
        self.viewport().update()

    def advance(self) -> None:
        """One animation step for the hatched 'working' bars."""
        self.phase = (self.phase + 1) % 11
        self.viewport().update()

    def _button_row_at(self, pos: QPoint) -> int:
        index = self.indexAt(pos)
        if not (self.removable and index.isValid()) or index.data(STATE_ROLE) != QUEUED:
            return -1
        return index.row() if remove_button_rect(self.visualRect(index)).contains(pos) else -1

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        hot = self._button_row_at(event.position().toPoint())
        if hot != self.hot_row:
            self.hot_row = hot
            self.viewport().update()
            self.viewport().setCursor(Qt.CursorShape.PointingHandCursor if hot >= 0 else Qt.CursorShape.ArrowCursor)
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self.hot_row = -1
        self.viewport().update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._button_row_at(event.position().toPoint()) >= 0:
            self.removeRequested.emit(self.indexAt(event.position().toPoint()).row())
            return  # the ✕ removes the row without changing the selection
        super().mousePressEvent(event)


class QueueHeader(QWidget):
    """The 28 px column-title strip above the list."""

    TITLES = ("#", "IMG", "ФАЙЛ", "ФОРМАТ", "ИСХОДНЫЙ", "РЕЗУЛЬТАТ", "")

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedHeight(28)
        self._right_margin = 0

    def set_right_margin(self, margin: int) -> None:
        if margin != self._right_margin:
            self._right_margin = margin
            self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        r = self.rect()
        p.fillRect(QRect(0, r.height() - 1, r.width(), 1), col("line"))
        p.setFont(font(10, spacing=0.1))
        p.setPen(col("mute"))
        for (x, w), title, index in zip(column_spans(r.width() - self._right_margin), self.TITLES, range(7), strict=True):
            flags = _V | (int(Qt.AlignmentFlag.AlignRight) if index == SIZE else 0)
            p.drawText(QRect(x, 0, w, r.height() - 1), flags, title)
        p.end()


class QueueList(QWidget):
    """Header + view; keeps the header aligned with the rows when the scroll bar appears."""

    def __init__(self, model: QueueModel, parent=None) -> None:
        super().__init__(parent)
        self.header = QueueHeader()
        self.view = QueueView(model)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.header)
        layout.addWidget(self.view, 1)
        self.view.verticalScrollBar().rangeChanged.connect(lambda *_: QTimer.singleShot(0, self._sync))

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._sync()

    def _sync(self) -> None:
        bar = self.view.verticalScrollBar()
        self.header.set_right_margin(bar.width() if bar.isVisibleTo(self.view) else 0)
