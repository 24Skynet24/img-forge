"""The ImgForge mark: a solid block that breaks apart into pixels (violet = the last pixel / output)."""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap

from gui.themes.tokens import LIGHT

# (x, y, w, h, colour role) on a 24-unit grid; "hole" is punched with the panel colour.
FULL = (
    (0, 0, 12, 24, "ink"),
    (12, 0, 6, 6, "ink"),
    (21, 0, 3, 3, "ink"),
    (18, 6, 6, 6, "ink"),
    (12, 12, 6, 6, "ink"),
    (18, 18, 6, 6, "violet"),
    (8, 16, 2, 2, "panel"),
)
# The same idea on a 4-unit grid, for 16-32 px where the detailed mark turns to mush.
SIMPLE = (
    (0, 0, 2, 4, "ink"),
    (2, 0, 1, 1, "ink"),
    (3, 1, 1, 1, "ink"),
    (2, 2, 1, 1, "ink"),
    (3, 3, 1, 1, "violet"),
)


def paint_mark(p: QPainter, rect: QRectF, colours: dict[str, str], simple: bool = False) -> None:
    """Draw the mark into ``rect`` using hard (non-antialiased) pixel edges."""
    units = 4 if simple else 24
    cell = rect.width() / units
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    p.setPen(Qt.PenStyle.NoPen)
    for x, y, w, h, role in SIMPLE if simple else FULL:
        p.setBrush(QColor(colours[role]))
        p.drawRect(QRectF(rect.x() + x * cell, rect.y() + y * cell, w * cell, h * cell))
    p.restore()


def mark_pixmap(size: int, colours: dict[str, str], simple: bool = False, background: str | None = None) -> QPixmap:
    """The mark as a pixmap, optionally on a square tile of ``background``."""
    pm = QPixmap(size, size)
    pm.fill(QColor(background) if background else Qt.GlobalColor.transparent)
    p = QPainter(pm)
    pad = 0.0 if background is None else size * 0.14
    paint_mark(p, QRectF(pad, pad, size - 2 * pad, size - 2 * pad), colours, simple)
    p.end()
    return pm


SIMPLE_UP_TO = 32  # icon sizes up to this use the simplified mark


def paint_icon(p: QPainter, size: int) -> None:
    """The application icon: ink mark on a paper tile with an ink outline.

    The single source of the .ico frames and of the icon shown in the window title bar, so both
    always look the same. Always drawn with the light palette, whatever the active theme.
    """
    colours = {"ink": LIGHT.ink, "violet": LIGHT.violet, "panel": LIGHT.panel}
    simple = size <= SIMPLE_UP_TO
    p.fillRect(QRectF(0, 0, size, size), QColor(LIGHT.panel))
    mark = (size * 3 // 4) // 4 * 4 if simple else round(size * 0.72)  # whole pixels per unit keep edges crisp
    offset = (size - mark) / 2
    paint_mark(p, QRectF(offset, offset, mark, mark), colours, simple)
    outline = max(1, size // 32)
    ink = QColor(LIGHT.ink)
    for rect in (
        QRectF(0, 0, size, outline), QRectF(0, size - outline, size, outline),
        QRectF(0, 0, outline, size), QRectF(size - outline, 0, outline, size),
    ):
        p.fillRect(rect, ink)
