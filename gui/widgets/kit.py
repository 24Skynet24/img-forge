"""Small custom-painted building blocks of the brutalist UI (buttons, chips, bars, hatching)."""
from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QEvent, QObject, QRect, QRectF, QSize, Qt
from PySide6.QtGui import QBrush, QColor, QFontMetrics, QPainter, QPen, QPixmap, QTransform
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QWidget

from gui.themes import tokens
from gui.themes.fonts import font
from gui.themes.mark import paint_icon, paint_mark

_KEYBOARD_REASONS = (
    Qt.FocusReason.TabFocusReason,
    Qt.FocusReason.BacktabFocusReason,
    Qt.FocusReason.ShortcutFocusReason,
)
_NAVIGATION_KEYS = (Qt.Key.Key_Tab, Qt.Key.Key_Backtab, Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down)


class InputTracker(QObject):
    """Remembers whether the user last navigated with the keyboard or the mouse.

    The violet focus ring is a keyboard affordance: it must not appear when focus merely moves
    because a clicked button was hidden or disabled.
    """

    keyboard = False

    def eventFilter(self, _watched, event) -> bool:  # noqa: N802
        kind = event.type()
        if kind == QEvent.Type.KeyPress and event.key() in _NAVIGATION_KEYS:
            InputTracker.keyboard = True
        elif kind in (QEvent.Type.MouseButtonPress, QEvent.Type.TouchBegin):
            InputTracker.keyboard = False
        return False


def install_input_tracker(app: QObject) -> InputTracker:
    """Start tracking keyboard vs mouse navigation application-wide."""
    tracker = InputTracker(app)
    app.installEventFilter(tracker)
    return tracker


class KbdFocus:
    """Mixin: ``_kbd_focus`` is True while the widget holds focus that came from keyboard navigation."""

    _kbd_focus = False

    def focusInEvent(self, event) -> None:  # noqa: N802
        self._kbd_focus = InputTracker.keyboard and event.reason() in _KEYBOARD_REASONS
        super().focusInEvent(event)  # type: ignore[misc]

    def focusOutEvent(self, event) -> None:  # noqa: N802
        self._kbd_focus = False
        super().focusOutEvent(event)  # type: ignore[misc]


@lru_cache(maxsize=256)
def _colour(hex_value: str, alpha: int | None) -> QColor:
    colour = QColor(hex_value)
    if alpha is not None:
        colour.setAlpha(alpha)
    return colour


def col(name: str, alpha: int | None = None) -> QColor:
    """A colour of the active theme by token name (cached: it is called thousands of times per repaint)."""
    return _colour(getattr(tokens.current(), name), alpha)


@lru_cache(maxsize=64)
def _hatch_pixmap(colour: str, background: str | None, period: int = 11, on: int = 5) -> QPixmap:
    """45° stripes (CSS ``repeating-linear-gradient(135deg, …)``) as a seamless tile."""
    pm = QPixmap(period, period)
    pm.fill(QColor(background) if background else Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setPen(QPen(QColor(colour), 1))
    for x in range(period):
        for y in range(period):
            if (x + y) % period < on:
                p.drawPoint(x, y)
    p.end()
    return pm


def hatch_brush(name: str, *, background: str | None = None, offset: float = 0.0) -> QBrush:
    """Hatch brush of a token colour; ``offset`` slides the stripes (progress animation)."""
    t = tokens.current()
    brush = QBrush(_hatch_pixmap(getattr(t, name), getattr(t, background) if background else None))
    if offset:
        brush.setTransform(QTransform.fromTranslate(offset, 0))
    return brush


def draw_frame(p: QPainter, rect: QRect, colour: QColor, width: int = 1) -> None:
    """A crisp rectangular border drawn inside ``rect``."""
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(colour)
    w = width
    p.drawRect(QRect(rect.left(), rect.top(), rect.width(), w))
    p.drawRect(QRect(rect.left(), rect.bottom() - w + 1, rect.width(), w))
    p.drawRect(QRect(rect.left(), rect.top() + w, w, rect.height() - 2 * w))
    p.drawRect(QRect(rect.right() - w + 1, rect.top() + w, w, rect.height() - 2 * w))
    p.restore()


def draw_focus(p: QPainter, rect: QRect) -> None:
    """The 2 px violet keyboard-focus ring."""
    draw_frame(p, rect, col("violet"), 2)


class Tx(QLabel):
    """A label with the design's typography. ``tone`` is one of ink / mute / vtext / inv."""

    def __init__(
        self,
        text: str = "",
        px: int = 12,
        weight: int = 400,
        tone: str = "ink",
        *,
        display: bool = False,
        spacing: float = 0.0,
        upper: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._upper = upper
        self.setFont(font(px, weight, display=display, spacing=spacing))
        self.setProperty("tone", tone)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setText(text)

    def setText(self, text: str) -> None:  # noqa: N802
        super().setText(text.upper() if self._upper else text)

    def set_tone(self, tone: str) -> None:
        self.setProperty("tone", tone)
        self.style().unpolish(self)
        self.style().polish(self)


class Rule(QFrame):
    """A 1 px divider; ``strong`` uses the ink colour, otherwise the soft line colour."""

    def __init__(self, vertical: bool = False, strong: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._strong = strong
        if vertical:
            self.setFixedWidth(1)
            self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        else:
            self.setFixedHeight(1)
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), col("ink" if self._strong else "line"))
        p.end()


class MarkWidget(QWidget):
    """The ImgForge mark in the colours of the active theme."""

    def __init__(self, size: int, simple: bool = False, hole: str = "panel", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._simple = simple
        self._hole = hole
        self.setFixedSize(size, size)

    def paintEvent(self, _event) -> None:  # noqa: N802
        t = tokens.current()
        p = QPainter(self)
        paint_mark(
            p, QRectF(self.rect()),
            {"ink": t.ink, "violet": t.violet, "panel": getattr(t, self._hole)},
            self._simple,
        )
        p.end()


class AppIcon(QWidget):
    """The application icon exactly as in assets/icon.ico (same painter), for the title bar."""

    def __init__(self, size: int = 16, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._size = size
        self.setFixedSize(size, size)

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        paint_icon(p, self._size)
        p.end()


class Btn(KbdFocus, QPushButton):
    """Flat bordered button: ink border, inverts on hover, hatched when disabled.

    ``kind``: "secondary" (ink border), "ghost" (soft border), "status" (disabled stays flat).
    ``glyph`` is a symbol pinned to the right edge.
    """

    def __init__(
        self,
        text: str = "",
        glyph: str = "",
        *,
        kind: str = "secondary",
        height: int = 32,
        px: int = 12,
        weight: int = 400,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(text, parent)
        self._glyph = glyph
        self._kind = kind
        self.setFont(font(px, weight))
        self.setFixedHeight(height)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def sizeHint(self) -> QSize:  # noqa: N802
        fm = QFontMetrics(self.font())
        width = 24 + fm.horizontalAdvance(self.text())
        if self._glyph:
            width += 12 + fm.horizontalAdvance(self._glyph)
        return QSize(width, self.height())

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return self.sizeHint()

    def enterEvent(self, event) -> None:  # noqa: N802
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        r = self.rect()
        enabled = self.isEnabled()
        hot = enabled and (self.underMouse() or self.isDown())
        if not enabled:
            if self._kind != "status":
                p.fillRect(r, hatch_brush("line2"))
            border, fg = col("line"), col("mute")
        elif hot:
            if self._kind == "ghost":
                p.fillRect(r, col("hover"))
                border, fg = col("ink"), col("ink")
            else:
                p.fillRect(r, col("ink"))
                border, fg = col("ink"), col("inv")
        else:
            if self._kind != "ghost":
                p.fillRect(r, col("panel"))
            border = col("line") if self._kind == "ghost" else col("ink")
            fg = col("ink")
        draw_frame(p, r, border)
        p.setFont(self.font())
        p.setPen(fg)
        text_rect = r.adjusted(12, 0, -12, 0)
        p.drawText(text_rect, int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft), self.text())
        if self._glyph:
            p.drawText(text_rect, int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight), self._glyph)
        if self._kbd_focus and enabled:
            draw_focus(p, r)
        p.end()


class ChipLabel(QLabel):
    """A tiny filled tag: ``lime`` (result), ``ink`` (inverse) or ``panel`` (plain)."""

    def __init__(
        self, text: str = "", variant: str = "lime", px: int = 11, weight: int = 700, parent: QWidget | None = None
    ) -> None:
        super().__init__(text, parent)
        self._variant = variant
        self.setFont(font(px, weight))
        self.setContentsMargins(8, 3, 8, 3)

    def sizeHint(self) -> QSize:  # noqa: N802
        fm = QFontMetrics(self.font())
        m = self.contentsMargins()
        return QSize(fm.horizontalAdvance(self.text()) + m.left() + m.right(), fm.height() + m.top() + m.bottom())

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        bg, fg = {
            "lime": ("lime", "onlime"),
            "ink": ("ink", "inv"),
            "panel": ("panel", "ink"),
            "mute": ("panel", "mute"),
        }[self._variant]
        p.fillRect(self.rect(), col(bg))
        p.setFont(self.font())
        p.setPen(col(fg))
        p.drawText(self.rect(), int(Qt.AlignmentFlag.AlignCenter), self.text())
        p.end()


class SegBar(QWidget):
    """24-segment progress bar: solid violet = done, hatched violet = in flight."""

    SEGMENTS = 24

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(14)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._total = 0
        self._done = 0
        self._inflight = 0
        self._phase = 0.0

    def set_progress(self, done: int, total: int, inflight: int = 0) -> None:
        self._done, self._total, self._inflight = done, total, inflight
        self.update()

    def advance(self) -> None:
        self._phase = (self._phase + 1) % 11
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        r = self.rect()
        p.fillRect(r, col("panel"))
        inner = r.adjusted(1, 1, -1, -1)
        total = max(1, self._total)
        done = min(self._done, total)
        done_w = round(inner.width() * done / total)
        fly_w = round(inner.width() * min(self._inflight, total - done) / total)
        p.fillRect(QRect(inner.left(), inner.top(), done_w, inner.height()), col("violet"))
        if fly_w:
            p.fillRect(
                QRect(inner.left() + done_w, inner.top(), fly_w, inner.height()),
                hatch_brush("violet", offset=self._phase),
            )
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col("panel"))
        step = inner.width() / self.SEGMENTS
        for i in range(1, self.SEGMENTS):
            p.drawRect(QRectF(inner.left() + i * step - 2, inner.top(), 2, inner.height()))
        draw_frame(p, r, col("ink"))
        p.end()


class Header(QWidget):
    """Numbered section header: ``/01  ИСТОЧНИКИ ........ info``."""

    def __init__(self, number: str, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._right = Tx("", 11, tone="mute")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(Tx(number, 12, 700, "vtext"))
        layout.addWidget(Tx(title, 12, 700, spacing=0.08, upper=True))
        layout.addStretch()
        layout.addWidget(self._right)

    def set_right(self, text: str) -> None:
        self._right.setText(text)


class Surface(QWidget):
    """A plain filled area with optional 1 px borders (each side takes a token name or None)."""

    def __init__(
        self,
        bg: str | None = "panel",
        *,
        top: str | None = None,
        bottom: str | None = None,
        left: str | None = None,
        right: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._bg = bg
        self._sides = {"top": top, "bottom": bottom, "left": left, "right": right}
        # A filled surface paints every pixel itself: tell Qt not to erase / repaint what is beneath it.
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, bg is not None)

    def set_background(self, bg: str | None) -> None:
        self._bg = bg
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, bg is not None)
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        r = self.rect()
        if self._bg:
            p.fillRect(r, col(self._bg))
        if self._sides["top"]:
            p.fillRect(QRect(0, 0, r.width(), 1), col(self._sides["top"]))
        if self._sides["bottom"]:
            p.fillRect(QRect(0, r.height() - 1, r.width(), 1), col(self._sides["bottom"]))
        if self._sides["left"]:
            p.fillRect(QRect(0, 0, 1, r.height()), col(self._sides["left"]))
        if self._sides["right"]:
            p.fillRect(QRect(r.width() - 1, 0, 1, r.height()), col(self._sides["right"]))
        p.end()


class ElidedTx(Tx):
    """A single-line label that elides with "…" instead of growing; ``text()`` stays the full text."""

    def __init__(
        self,
        text: str = "",
        px: int = 12,
        weight: int = 400,
        tone: str = "ink",
        *,
        spacing: float = 0.0,
        upper: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        self._full = ""
        super().__init__(text, px, weight, tone, spacing=spacing, upper=upper, parent=parent)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(0)

    def setText(self, text: str) -> None:  # noqa: N802
        self._full = text.upper() if self._upper else text
        self.setToolTip(self._full)
        super().setText(text)

    def text(self) -> str:
        return self._full

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setFont(self.font())
        p.setPen(col({"mute": "mute", "vtext": "vtext", "inv": "inv"}.get(self.property("tone"), "ink")))
        elided = QFontMetrics(self.font()).elidedText(self._full, Qt.TextElideMode.ElideRight, self.width())
        p.drawText(self.rect(), int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft), elided)
        p.end()
