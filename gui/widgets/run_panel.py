"""/04 ЗАПУСК: the start button that turns into live progress while a batch runs."""
from __future__ import annotations

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from gui.themes.fonts import font
from gui.widgets.kit import Btn, Header, KbdFocus, SegBar, Surface, Tx, col, draw_focus, draw_frame, hatch_brush

_SHADOW = 3  # px the primary button lifts on hover (and reserves around itself)


class StartButton(KbdFocus, QPushButton):
    """The one primary action: ink slab with a display-font label; lifts on a violet shadow on hover."""

    def __init__(self, text: str = "Начать", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setFixedHeight(52 + 2 * _SHADOW)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(220, 52 + 2 * _SHADOW)

    def enterEvent(self, event) -> None:  # noqa: N802
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        body = self.rect().adjusted(_SHADOW, _SHADOW, -_SHADOW, -_SHADOW)
        enabled = self.isEnabled()
        lifted = enabled and self.underMouse() and not self.isDown()
        if lifted:
            p.fillRect(body, col("violet"))
            body = body.translated(-_SHADOW, -_SHADOW)
        if enabled:
            p.fillRect(body, col("ink"))
            text_colour, tile_bg, tile_fg = col("inv"), col("inv"), col("ink")
        else:
            p.fillRect(body, hatch_brush("line2"))
            draw_frame(p, body, col("line"))
            text_colour, tile_bg, tile_fg = col("mute"), None, col("mute")
        p.setFont(font(22, 600, display=True, spacing=0.06))
        p.setPen(text_colour)
        p.drawText(body.adjusted(18, 0, 0, 0), int(Qt.AlignmentFlag.AlignVCenter), self.text().upper())
        tile = QRect(body.right() - 8 - 36 + 1, body.top() + 8, 36, 36)
        if tile_bg is not None:
            p.fillRect(tile, tile_bg)
        else:
            draw_frame(p, tile, col("line"))
        p.setFont(font(18, 700 if enabled else 400))
        p.setPen(tile_fg)
        p.drawText(tile, int(Qt.AlignmentFlag.AlignCenter), "↗")
        if self._kbd_focus and enabled:
            draw_focus(p, self.rect())
        p.end()


class RunPanel(Surface):
    """Header with the launch info, the start button and (while running) progress + cancel."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("bg", top="ink", parent=parent)
        self.start = StartButton()
        self.cancel = Btn("Отменить", "■", height=30, weight=700)
        self._header = Header("/04", "ЗАПУСК")
        self._percent = Tx("0%", 22, 600, display=True)
        self._bar = SegBar()
        self._count = Tx("", 11, 700)
        self._meta = Tx("", 10, tone="mute", spacing=0.06)

        self._progress = QWidget()
        top = QHBoxLayout()
        top.setSpacing(10)
        top.addWidget(self._percent)
        top.addWidget(self._bar, 1)
        top.addWidget(self._count)
        bottom = QHBoxLayout()
        bottom.setSpacing(10)
        bottom.addWidget(self._meta, 1)
        bottom.addWidget(self.cancel)
        progress = QVBoxLayout(self._progress)
        progress.setContentsMargins(0, 0, 0, 0)
        progress.setSpacing(6)
        progress.addLayout(top)
        progress.addLayout(bottom)
        self._progress.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 12, 20, 16)
        layout.setSpacing(10)
        layout.addWidget(self._header)
        # the start button reserves a few px around itself for its hover lift
        holder = QHBoxLayout()
        holder.setContentsMargins(-_SHADOW, -_SHADOW, -_SHADOW, -_SHADOW)
        holder.addWidget(self.start)
        layout.addLayout(holder)
        layout.addWidget(self._progress)

    def set_info(self, text: str) -> None:
        self._header.set_right(text)

    def set_running(self, running: bool) -> None:
        self.start.setVisible(not running)
        self._progress.setVisible(running)

    def set_progress(self, done: int, total: int, inflight: int, meta: str) -> None:
        percent = 100 * done // total if total else 0
        self._percent.setText(f"{percent}%")
        self._bar.set_progress(done, total, inflight)
        self._count.setText(f"{done} / {total}")
        self._meta.setText(meta)

    def advance(self) -> None:
        self._bar.advance()
