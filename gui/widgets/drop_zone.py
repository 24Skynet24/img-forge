"""The empty state: a big drop zone."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from gui.themes.tokens import Tokens


def _draw_icon(tokens: Tokens, size: int = 96) -> QPixmap:
    """A simple 'image' pictogram (frame, sun, mountains) in the accent colour."""
    ratio = 2
    pm = QPixmap(size * ratio, size * ratio)
    pm.setDevicePixelRatio(ratio)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    accent = QColor(tokens.accent)
    pen = QPen(accent, 3.5)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    frame = QRectF(10, 16, size - 20, size - 32)
    p.drawRoundedRect(frame, 10, 10)
    p.setBrush(accent)
    p.drawEllipse(QPointF(size * 0.68, size * 0.38), 6, 6)
    path = QPainterPath()
    path.moveTo(16, size - 24)
    path.lineTo(size * 0.38, size * 0.48)
    path.lineTo(size * 0.55, size * 0.66)
    path.lineTo(size * 0.68, size * 0.55)
    path.lineTo(size - 16, size - 24)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(path)
    p.end()
    return pm


class DropZone(QFrame):
    """Shown while the queue is empty; also offers the add buttons."""

    addFilesRequested = Signal()
    addFolderRequested = Signal()

    def __init__(self, tokens: Tokens, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("dropZone")
        self._icon = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        title = QLabel("Перетащите фото или папки сюда", alignment=Qt.AlignmentFlag.AlignCenter)
        title.setObjectName("dropTitle")
        hint = QLabel(
            "PNG, JPEG, WebP, AVIF, GIF, BMP, TIFF, HEIC · папки с любой вложенностью",
            alignment=Qt.AlignmentFlag.AlignCenter,
        )
        hint.setProperty("muted", True)
        files = QPushButton("Добавить файлы")
        files.setObjectName("primary")
        files.setCursor(Qt.CursorShape.PointingHandCursor)
        folder = QPushButton("Добавить папку")
        folder.setCursor(Qt.CursorShape.PointingHandCursor)
        files.clicked.connect(self.addFilesRequested)
        folder.clicked.connect(self.addFolderRequested)

        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(files)
        buttons.addWidget(folder)
        buttons.addStretch()
        layout = QVBoxLayout(self)
        layout.addStretch()
        layout.addWidget(self._icon)
        layout.addSpacing(8)
        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addSpacing(18)
        layout.addLayout(buttons)
        layout.addStretch()
        self.set_tokens(tokens)

    def set_tokens(self, tokens: Tokens) -> None:
        self._icon.setPixmap(_draw_icon(tokens))

    def set_highlighted(self, on: bool) -> None:
        """Visual feedback while files are dragged over the window."""
        self.setProperty("highlight", on)
        self.style().unpolish(self)
        self.style().polish(self)
