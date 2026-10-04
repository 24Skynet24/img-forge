"""Small status widgets of the main window: the top-bar readout cell and the status dot."""
from __future__ import annotations

from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QVBoxLayout, QWidget

from gui.widgets.kit import ElidedTx, Surface, Tx, col, draw_frame


class Readout(Surface):
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


class StatusDot(QWidget):
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
