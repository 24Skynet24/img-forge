"""Custom 32 px window title bar (the window is frameless)."""
from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QPainter, QPen
from PySide6.QtWidgets import QAbstractButton, QHBoxLayout, QWidget

from gui.widgets.kit import AppIcon, Surface, Tx, col, draw_frame


class _CaptionButton(QAbstractButton):
    """Minimise / maximise-restore / close glyph button, 46 × 32 px."""

    def __init__(self, kind: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.kind = kind
        self.restore = False  # maximise button: show the "restore" glyph
        self.setFixedSize(46, 32)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def enterEvent(self, event) -> None:  # noqa: N802
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        r = self.rect()
        hot = self.underMouse()
        close = self.kind == "close"
        if hot:
            p.fillRect(r, col("ink") if close else col("hover"))
        fg = col("inv") if (hot and close) else col("ink")
        cx, cy = r.width() // 2, r.height() // 2
        if self.kind == "min":
            p.fillRect(QRect(cx - 5, cy, 10, 1), fg)
        elif self.kind == "max":
            if self.restore:
                draw_frame(p, QRect(cx - 4, cy - 2, 8, 8), fg)
                p.fillRect(QRect(cx - 2, cy - 4, 7, 1), fg)
                p.fillRect(QRect(cx + 5, cy - 4, 1, 7), fg)
            else:
                draw_frame(p, QRect(cx - 5, cy - 5, 10, 10), fg)
        else:
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            p.setPen(QPen(fg, 1.2))
            p.drawLine(cx - 5, cy - 5, cx + 5, cy + 5)
            p.drawLine(cx - 5, cy + 5, cx + 5, cy - 5)
        p.end()


class TitleBar(Surface):
    """Mark, app name, live info on the left; window buttons on the right."""

    minimizeRequested = Signal()
    maximizeRequested = Signal()
    closeRequested = Signal()

    HEIGHT = 32

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("panel", bottom="line", parent=parent)
        self.setFixedHeight(self.HEIGHT)
        self._info = Tx("", 11, tone="mute")
        self._info.setMinimumWidth(0)
        self._min = _CaptionButton("min")
        self._max = _CaptionButton("max")
        self._close = _CaptionButton("close")
        self._min.clicked.connect(self.minimizeRequested)
        self._max.clicked.connect(self.maximizeRequested)
        self._close.clicked.connect(self.closeRequested)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(AppIcon(16))
        layout.addWidget(Tx("ImgForge", 12))
        layout.addWidget(self._info, 1)
        layout.setSpacing(10)
        buttons = QHBoxLayout()
        buttons.setSpacing(0)
        for button in (self._min, self._max, self._close):
            buttons.addWidget(button)
        layout.addLayout(buttons)

    def set_info(self, text: str) -> None:
        self._info.setText(text)

    def set_maximized(self, maximized: bool) -> None:
        self._max.restore = maximized
        self._max.update()

    def is_caption_at(self, pos: QPoint) -> bool:
        """True where dragging moves the window (everything except the three buttons)."""
        child = self.childAt(pos)
        return not isinstance(child, _CaptionButton)

    # Fallback for platforms where the native hit-test is not used.
    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self.window().windowHandle() is not None:
            self.window().windowHandle().startSystemMove()
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self.is_caption_at(event.position().toPoint()):
            self.maximizeRequested.emit()
        super().mouseDoubleClickEvent(event)
