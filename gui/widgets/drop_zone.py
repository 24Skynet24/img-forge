"""The empty state: a big drop zone with corner brackets, a blueprint grid and live readouts."""
from __future__ import annotations

from PySide6.QtCore import QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from core.utils import plural
from gui.themes.fonts import font
from gui.widgets.kit import Btn, ChipLabel, Tx, col, draw_frame


class _Glyph(QWidget):
    """Crosshair box with a download arrow; turns violet while files are dragged over."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(96, 96)
        self.drag = False

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        accent = col("violet") if self.drag else col("ink")
        weight = 2 if self.drag else 1
        box = QRect(12, 12, 72, 72)
        p.fillRect(box, col("panel"))
        p.fillRect(QRect(48 - weight // 2, 0, weight, 96), accent)
        p.fillRect(QRect(0, 48 - weight // 2, 96, weight), accent)
        p.fillRect(box.adjusted(1, 1, -1, -1), col("panel"))
        draw_frame(p, box, accent, weight)
        size = 40 if self.drag else 32
        inner = QRect(0, 0, size, size)
        inner.moveCenter(box.center())
        p.fillRect(inner, col("violet") if self.drag else col("ink"))
        p.setFont(font(22 if self.drag else 18, 700))
        p.setPen(Qt.GlobalColor.white if self.drag else col("inv"))
        p.drawText(inner, int(Qt.AlignmentFlag.AlignCenter), "↓")
        p.end()


class DropZone(QWidget):
    """Shown while the queue is empty; also offers the add buttons."""

    addFilesRequested = Signal()
    addFolderRequested = Signal()

    TITLE = "Перетащите фото или папки сюда"
    TITLE_WRAPPED = "Перетащите фото\nили папки сюда"
    DRAG_TITLE = "Отпустите, чтобы добавить"
    DRAG_TITLE_WRAPPED = "Отпустите,\nчтобы добавить"
    HINT = "PNG, JPEG, WebP, AVIF, GIF, BMP, TIFF, HEIC · папки с любой вложенностью"
    HINT_WRAPPED = "PNG, JPEG, WebP, AVIF, GIF, BMP, TIFF, HEIC\nпапки с любой вложенностью"

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._wrapped = False
        self._text_state: tuple[bool, bool] | None = None
        self._drag = False
        self._readout = ""
        self._drag_files = self._drag_dirs = 0
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumHeight(300)

        self._glyph = _Glyph()
        self._title = Tx(self.TITLE, 40, 600, display=True, spacing=0.01, upper=True)
        self._hint = Tx(self.HINT, 12, tone="mute")
        for label in (self._title, self._hint):
            # full-width, centred text that may shrink to nothing: the zone switches to two-line
            # text (see _fit_text) before it runs out of room, so the layout never needs a minimum
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            label.setMinimumWidth(0)

        files = Btn("Добавить файлы", "→", height=40, weight=700)
        folder = Btn("Добавить папку", "→", height=40, weight=700)
        files.clicked.connect(self.addFilesRequested)
        folder.clicked.connect(self.addFolderRequested)
        self._buttons = QWidget()
        buttons = QHBoxLayout(self._buttons)
        buttons.setContentsMargins(0, 4, 0, 0)
        buttons.setSpacing(8)
        buttons.addWidget(files)
        buttons.addWidget(folder)

        self._chips = QWidget()
        chips = QHBoxLayout(self._chips)
        chips.setContentsMargins(0, 0, 0, 0)
        chips.setSpacing(0)
        self._chip_files = ChipLabel("", "lime", px=12)
        self._chip_dirs = ChipLabel("", "panel", px=12, weight=400)
        chips.addWidget(self._chip_files)
        chips.addWidget(self._chip_dirs)
        self._chips.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)
        layout.addStretch()
        layout.addWidget(self._glyph, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self._title)
        layout.addWidget(self._hint)
        layout.addWidget(self._chips, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self._buttons, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch()

    # ------------------------------------------------------------------ public

    def set_readout(self, text: str) -> None:
        """Bottom-right readout, e.g. ``OUT → WEBP · THR 12``."""
        self._readout = text
        self.update()

    def set_drag_info(self, files: int, dirs: int) -> None:
        """What is being dragged over the window (shown while highlighted)."""
        self._drag_files, self._drag_dirs = files, dirs
        self._chip_files.setText(f"+{files} {plural(files, ('файл', 'файла', 'файлов'))}" if files else "")
        self._chip_files.setVisible(files > 0)
        self._chip_dirs.setText(f"{dirs} {plural(dirs, ('папка', 'папки', 'папок'))}" if dirs else "")
        self._chip_dirs.setVisible(dirs > 0)
        self.update()

    def set_highlighted(self, on: bool) -> None:
        """Visual feedback while files are dragged over the window."""
        if on == self._drag:
            return
        self._drag = on
        self._glyph.drag = on
        self._glyph.update()
        self._fit_text()
        self._hint.setVisible(not on)
        self._buttons.setVisible(not on)
        self._chips.setVisible(on)
        self.update()

    @property
    def highlighted(self) -> bool:
        return self._drag

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(600, 400)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._fit_text()

    def _fit_text(self) -> None:
        """One line of title/hint when it fits, two balanced lines when the zone is narrow."""
        title = self.DRAG_TITLE if self._drag else self.TITLE
        title_w = QFontMetrics(self._title.font()).horizontalAdvance(title.upper())
        hint_w = QFontMetrics(self._hint.font()).horizontalAdvance(self.HINT)
        wrapped = self.width() < max(title_w, hint_w) + 24 * 2 + 16 * 2 + 16
        state = (wrapped, self._drag)
        if state == self._text_state:
            return  # no relayout on every resize step, only when the wording actually changes
        self._text_state = state
        self._wrapped = wrapped
        if self._drag:
            self._title.setText(self.DRAG_TITLE_WRAPPED if wrapped else self.DRAG_TITLE)
        else:
            self._title.setText(self.TITLE_WRAPPED if wrapped else self.TITLE)
        self._hint.setText(self.HINT_WRAPPED if wrapped else self.HINT)

    # ------------------------------------------------------------------ painting

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        outer = self.rect().adjusted(16, 16, -16, -16)
        drag = self._drag
        accent = col("violet")
        if drag:
            p.fillRect(outer, col("violet", 23))
        p.save()
        p.setClipRect(outer)
        grid = col("violet", 56) if drag else col("line2")
        p.setPen(QPen(grid, 1))
        for x in range(outer.left(), outer.right(), 32):
            p.drawLine(x, outer.top(), x, outer.bottom())
        for y in range(outer.top(), outer.bottom(), 32):
            p.drawLine(outer.left(), y, outer.right(), y)
        p.restore()

        if drag:
            draw_frame(p, outer, accent, 2)
        else:
            pen = QPen(col("mute"), 1, Qt.PenStyle.CustomDashLine)
            pen.setDashPattern([4, 3])
            p.setPen(pen)
            p.drawRect(QRectF(outer).adjusted(0.5, 0.5, -0.5, -0.5))
            # ruler ticks along the top edge
            p.setPen(QPen(col("mute"), 1))
            for x in range(outer.left() + 24, outer.right() - 24, 16):
                p.drawLine(x, outer.top() + 1, x, outer.top() + 6)

        # corner brackets
        size, weight = (20, 3) if drag else (16, 2)
        ink = col("ink")
        for cx, cy, dx, dy in (
            (outer.left(), outer.top(), 1, 1),
            (outer.right() + 1, outer.top(), -1, 1),
            (outer.left(), outer.bottom() + 1, 1, -1),
            (outer.right() + 1, outer.bottom() + 1, -1, -1),
        ):
            horizontal = QRect(min(cx, cx + dx * size), cy if dy > 0 else cy - weight, size, weight)
            vertical = QRect(cx if dx > 0 else cx - weight, min(cy, cy + dy * size), weight, size)
            p.fillRect(horizontal, ink)
            p.fillRect(vertical, ink)

        # readouts in the corners
        tone = col("vtext") if drag else col("mute")
        p.setFont(font(10, 700 if drag else 400, spacing=0.08))
        p.setPen(tone)
        left, right = outer.left() + 24, outer.right() - 24
        width = right - left
        top, bottom = outer.top() + 12, outer.bottom() - 28
        n = self._drag_files + self._drag_dirs
        corners = (
            (QRect(left, top, width, 16), Qt.AlignmentFlag.AlignLeft, "> DRAG-OVER · ОБНАРУЖЕНО_" if drag else "> ОЖИДАНИЕ ВВОДА_"),
            (QRect(left, top, width, 16), Qt.AlignmentFlag.AlignRight, f"ОБЪЕКТОВ {n}" if drag else "FILES 000 / 0 B"),
            (
                QRect(left, bottom, width, 16),
                Qt.AlignmentFlag.AlignLeft,
                f"DIRS {self._drag_dirs} · FILES {self._drag_files}" if drag else "IN: 8 FMT · DEPTH ∞",
            ),
            (QRect(left, bottom, width, 16), Qt.AlignmentFlag.AlignRight, self._readout),
        )
        for rect, align, text in corners:
            p.drawText(rect, int(align | Qt.AlignmentFlag.AlignVCenter), text)
        p.end()


class DropStrip(QPushButton):
    """Slim dashed drop target under the list: click to add files, highlights while dragging."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._count = ""
        self._drag = False
        self.setFixedHeight(44)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def set_count(self, text: str) -> None:
        self._count = text
        self.update()

    def set_highlighted(self, on: bool) -> None:
        self._drag = on
        self.update()

    def enterEvent(self, event) -> None:  # noqa: N802
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        r = self.rect()
        hot = self.underMouse() or self._drag
        if self._drag:
            p.fillRect(r, col("violet", 23))
            draw_frame(p, r, col("violet"), 2)
        else:
            pen = QPen(col("ink") if hot else col("mute"), 1, Qt.PenStyle.CustomDashLine)
            pen.setDashPattern([4, 3])
            p.setPen(pen)
            p.drawRect(QRectF(r).adjusted(0.5, 0.5, -0.5, -0.5))
        fg = col("ink") if hot else col("mute")
        box = QRect(14, (r.height() - 18) // 2, 18, 18)
        draw_frame(p, box, fg)
        p.setFont(font(12))
        p.setPen(fg)
        p.drawText(box, int(Qt.AlignmentFlag.AlignCenter), "+")
        p.setFont(font(11))
        p.drawText(
            QRect(44, 0, r.width() - 200, r.height()), int(Qt.AlignmentFlag.AlignVCenter), "Перетащите фото или папки сюда"
        )
        p.setFont(font(11, spacing=0.06))
        p.drawText(
            QRect(0, 0, r.width() - 14, r.height()),
            int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight),
            self._count,
        )
        p.end()
