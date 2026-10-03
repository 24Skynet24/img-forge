"""Custom-painted form controls of the settings panel (mode rows, dropdown, slider, checkbox, stepper)."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QSlider,
    QStyle,
    QStyledItemDelegate,
    QWidget,
)

from gui.themes.fonts import font
from gui.widgets.kit import KbdFocus, col, draw_focus, draw_frame, hatch_brush

DESC_ROLE = Qt.ItemDataRole.UserRole + 10  # the dropdown's secondary text ("alpha · animation")


def _triangle_down(p: QPainter, centre: QPointF, colour, half: float = 4.0) -> None:
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(colour)
    p.drawPolygon(
        QPolygonF(
            [
                QPointF(centre.x() - half, centre.y() - half / 2),
                QPointF(centre.x() + half + 1, centre.y() - half / 2),
                QPointF(centre.x() + 0.5, centre.y() + half / 2 + 1),
            ]
        )
    )
    p.restore()


class ModeButton(KbdFocus, QRadioButton):
    """One processing mode: a bordered row that inverts when selected."""

    def __init__(self, label: str, code: str, parent: QWidget | None = None) -> None:
        super().__init__(label, parent)
        self._code = code
        self.setFixedHeight(36)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFont(font(12))

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(200, 36)

    def hitButton(self, pos) -> bool:  # noqa: N802
        return self.rect().contains(pos)

    def enterEvent(self, event) -> None:  # noqa: N802
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        r = self.rect()
        enabled, checked = self.isEnabled(), self.isChecked()
        if not enabled:
            p.fillRect(r, hatch_brush("line2"))
            border, fg, box = col("line"), col("mute"), col("line")
        elif checked:
            p.fillRect(r, col("ink"))
            border, fg, box = col("ink"), col("inv"), col("inv")
        else:
            border = col("ink") if self.underMouse() else col("line")
            fg, box = col("ink"), col("ink")
        draw_frame(p, r, border)
        indicator = QRect(12, (r.height() - 12) // 2, 12, 12)
        draw_frame(p, indicator, box)
        if checked and enabled:
            p.fillRect(indicator.adjusted(3, 3, -3, -3), col("violet"))
        p.setPen(fg)
        p.setFont(font(12))
        p.drawText(QRect(36, 0, r.width() - 36 - 70, r.height()), int(Qt.AlignmentFlag.AlignVCenter), self.text())
        p.setFont(font(10, spacing=0.06))
        p.drawText(
            QRect(0, 0, r.width() - 12, r.height()),
            int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight),
            self._code,
        )
        if self._kbd_focus and enabled:
            draw_focus(p, r)
        p.end()


class _FormatDelegate(QStyledItemDelegate):
    """Dropdown rows: bold label, muted description; the current row is inverted."""

    def sizeHint(self, option, index) -> QSize:  # noqa: N802
        return QSize(option.rect.width(), 30)

    def paint(self, painter: QPainter, option, index) -> None:
        r = option.rect
        current = bool(option.state & QStyle.StateFlag.State_Selected)
        hot = bool(option.state & QStyle.StateFlag.State_MouseOver)
        if current:
            painter.fillRect(r, col("ink"))
            fg, sub = col("inv"), col("inv")
        else:
            painter.fillRect(r, col("hover") if hot else col("panel"))
            fg, sub = col("ink"), col("mute")
        painter.setPen(fg)
        painter.setFont(font(12, 700))
        painter.drawText(
            QRect(r.left() + 12, r.top(), 52, r.height()),
            int(Qt.AlignmentFlag.AlignVCenter),
            index.data(Qt.ItemDataRole.DisplayRole),
        )
        painter.setPen(sub)
        painter.setFont(font(10))
        painter.drawText(
            QRect(r.left() + 64, r.top(), r.width() - 72, r.height()),
            int(Qt.AlignmentFlag.AlignVCenter),
            index.data(DESC_ROLE) or "",
        )


class FormatCombo(KbdFocus, QComboBox):
    """Output-format dropdown: ``WEBP  .webp                ▼``."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(36)
        self.setItemDelegate(_FormatDelegate(self))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFont(font(12))

    def add_format(self, label: str, data, extension: str, description: str) -> None:
        self.addItem(label.upper(), data)
        index = self.count() - 1
        self.setItemData(index, description, DESC_ROLE)
        self.setItemData(index, extension, Qt.ItemDataRole.UserRole + 11)

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
        hot = enabled and self.underMouse()
        cell = QRect(r.width() - 36, 0, 36, r.height())
        if not enabled:
            p.fillRect(r, hatch_brush("line2"))
            border, fg = col("line"), col("mute")
        else:
            p.fillRect(r, col("hover") if hot else col("bg"))
            border, fg = col("ink"), col("ink")
        draw_frame(p, r, border)
        p.fillRect(QRect(cell.left(), 0, 1, r.height()), border)
        if hot:
            p.fillRect(cell.adjusted(1, 0, 0, 0), col("ink"))
        p.setPen(fg)
        p.setFont(font(13, 700))
        label = self.currentText()
        p.drawText(QRect(12, 0, 200, r.height()), int(Qt.AlignmentFlag.AlignVCenter), label)
        extension = self.currentData(Qt.ItemDataRole.UserRole + 11) or ""
        p.setPen(col("mute"))
        p.setFont(font(11))
        label_w = QFontMetrics(font(13, 700)).horizontalAdvance(label)
        p.drawText(QRect(12 + label_w + 10, 0, 200, r.height()), int(Qt.AlignmentFlag.AlignVCenter), extension)
        arrow = col("inv") if hot else (col("mute") if not enabled else col("ink"))
        _triangle_down(p, QPointF(cell.center().x() + 0.5, r.height() / 2), arrow)
        if self._kbd_focus and enabled:
            draw_focus(p, r)
        p.end()


class StepSlider(KbdFocus, QSlider):
    """Discrete slider: a 2 px rail, tick marks and a square handle that turns violet on hover."""

    MARGIN = 6

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.setFixedHeight(26)
        self.setPageStep(1)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(200, 26)

    def _x_of(self, value: int) -> float:
        span = max(1, self.maximum() - self.minimum())
        return self.MARGIN + (value - self.minimum()) / span * (self.width() - 2 * self.MARGIN)

    def _value_at(self, x: float) -> int:
        span = self.maximum() - self.minimum()
        usable = max(1, self.width() - 2 * self.MARGIN)
        frac = min(1.0, max(0.0, (x - self.MARGIN) / usable))
        return self.minimum() + round(frac * span)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.setSliderDown(True)
            self.setValue(self._value_at(event.position().x()))
            self.setFocus(Qt.FocusReason.MouseFocusReason)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self.isSliderDown():
            self.setValue(self._value_at(event.position().x()))
        self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self.setSliderDown(False)
        self.update()

    def enterEvent(self, event) -> None:  # noqa: N802
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        enabled = self.isEnabled()
        rail, fill, tick = (col("line"), col("ink"), col("ink")) if enabled else (col("line2"), col("line"), col("line"))
        w = self.width()
        p.fillRect(QRect(0, 12, w, 2), rail)
        x = self._x_of(self.value())
        p.fillRect(QRectF(0, 11, x, 4), fill)
        for i in range(self.minimum(), self.maximum() + 1):
            p.fillRect(QRectF(self._x_of(i) - 0.5, 3, 1, 6), tick)
        hot = enabled and (self.underMouse() or self.isSliderDown())
        size = QSize(16, 20) if hot else QSize(12, 16)
        handle = QRect(round(x - size.width() / 2), 13 - size.height() // 2 + 0, size.width(), size.height())
        if enabled:
            p.fillRect(handle.adjusted(-2, -2, 2, 2), col("panel"))
            p.fillRect(handle, col("violet") if hot else col("ink"))
            if self._kbd_focus:
                draw_focus(p, handle.adjusted(-4, -4, 4, 4))
        else:
            p.fillRect(handle, hatch_brush("line2", background="panel"))
            draw_frame(p, handle, col("line"))
        p.end()


class MetaCheck(KbdFocus, QCheckBox):
    """Checkbox with a hint line: a 16 px square that fills with ink and shows a tick."""

    def __init__(self, text: str, hint: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self._hint = hint
        self.setFixedHeight(34)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFont(font(12))

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(220, 34)

    def hitButton(self, pos) -> bool:  # noqa: N802
        return self.rect().contains(pos)

    def enterEvent(self, event) -> None:  # noqa: N802
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        enabled, checked = self.isEnabled(), self.isChecked()
        hot = enabled and self.underMouse()
        box = QRect(0, 1, 16, 16)
        if hot:
            p.fillRect(box.translated(3, 3), col("violet"))
        if checked:
            p.fillRect(box, col("ink") if enabled else col("line"))
        else:
            p.fillRect(box, col("panel"))
        draw_frame(p, box, col("ink") if enabled else col("line"))
        if checked:
            pen = QPen(col("inv") if enabled else col("panel"), 2)
            pen.setCapStyle(Qt.PenCapStyle.SquareCap)
            p.setPen(pen)
            p.drawPolyline(QPolygonF([QPointF(3.5, 8.5), QPointF(6.5, 11.5), QPointF(12.5, 5)]))
        if self._kbd_focus and enabled:
            draw_frame(p, box.adjusted(-3, -3, 3, 3), col("violet"), 2)
        p.setFont(font(12))
        p.setPen(col("ink") if enabled else col("mute"))
        text_rect = QRect(26, 0, self.width() - 26, 16)
        p.drawText(text_rect, int(Qt.AlignmentFlag.AlignVCenter), self.text())
        if hot:
            fm = QFontMetrics(font(12))
            p.fillRect(QRect(26, 16, fm.horizontalAdvance(self.text()), 1), col("ink"))
        p.setFont(font(10))
        p.setPen(col("mute"))
        p.drawText(QRect(26, 17, self.width() - 26, 16), int(Qt.AlignmentFlag.AlignVCenter), self._hint)
        p.end()


class Stepper(KbdFocus, QWidget):
    """``− [ 12 ] +`` integer stepper."""

    valueChanged = Signal(int)

    BTN, VAL = 30, 44

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._min, self._max, self._value = 1, 32, 1
        self._hot = -1  # 0 = minus, 2 = plus
        self.setFixedSize(2 * self.BTN + self.VAL + 2, 30)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def value(self) -> int:
        return self._value

    def setRange(self, low: int, high: int) -> None:  # noqa: N802
        self._min, self._max = low, high
        self.setValue(self._value)

    def setValue(self, value: int) -> None:  # noqa: N802
        value = max(self._min, min(self._max, int(value)))
        if value != self._value:
            self._value = value
            self.update()
            self.valueChanged.emit(value)
        else:
            self.update()

    def _cell_at(self, x: float) -> int:
        if x < self.BTN + 1:
            return 0
        if x >= self.BTN + self.VAL + 1:
            return 2
        return 1

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        cell = self._cell_at(event.position().x())
        if cell == 0:
            self.setValue(self._value - 1)
        elif cell == 2:
            self.setValue(self._value + 1)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        cell = self._cell_at(event.position().x())
        hot = cell if cell != 1 else -1
        if hot != self._hot:
            self._hot = hot
            self.update()

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hot = -1
        self.update()
        super().leaveEvent(event)

    def wheelEvent(self, event) -> None:  # noqa: N802
        if self.isEnabled():
            self.setValue(self._value + (1 if event.angleDelta().y() > 0 else -1))

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Up, Qt.Key.Key_Right, Qt.Key.Key_Plus):
            self.setValue(self._value + 1)
        elif event.key() in (Qt.Key.Key_Down, Qt.Key.Key_Left, Qt.Key.Key_Minus):
            self.setValue(self._value - 1)
        else:
            super().keyPressEvent(event)

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        r = self.rect()
        enabled = self.isEnabled()
        border = col("ink") if enabled else col("line")
        p.fillRect(r, hatch_brush("line2") if not enabled else col("panel"))
        minus = QRect(1, 1, self.BTN, r.height() - 2)
        value = QRect(1 + self.BTN, 1, self.VAL + 1, r.height() - 2)
        plus = QRect(1 + self.BTN + self.VAL + 1, 1, self.BTN, r.height() - 2)
        if enabled:
            p.fillRect(value, col("bg"))
        for cell, index in ((minus, 0), (plus, 2)):
            if enabled and self._hot == index:
                p.fillRect(cell, col("ink"))
        draw_frame(p, r, border)
        p.fillRect(QRect(value.left() - 1, 1, 1, r.height() - 2), border)
        p.fillRect(QRect(value.right(), 1, 1, r.height() - 2), border)
        fg = col("ink") if enabled else col("mute")
        p.setFont(font(13, 700))
        for cell, symbol, index in ((minus, "−", 0), (plus, "+", 2)):
            p.setPen(col("inv") if enabled and self._hot == index else fg)
            p.drawText(cell, int(Qt.AlignmentFlag.AlignCenter), symbol)
        p.setPen(fg)
        p.drawText(value, int(Qt.AlignmentFlag.AlignCenter), str(self._value))
        if self._kbd_focus and enabled:
            draw_frame(p, value.adjusted(-2, -2, 2, 2), col("violet"), 2)
        p.end()


class ColorField(KbdFocus, QPushButton):
    """The background-colour field: swatch, hex value and RGB readout."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rgb = (255, 255, 255)
        self.setFixedHeight(36)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_rgb(self, rgb: tuple[int, int, int]) -> None:
        self._rgb = rgb
        self.update()

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(200, 36)

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
        if enabled:
            p.fillRect(r, col("bg"))
            border = col("ink") if self.underMouse() else col("line")
        else:
            p.fillRect(r, hatch_brush("line2"))
            border = col("line")
        draw_frame(p, r, border)
        swatch = QRect(6, 6, 24, 24)
        p.fillRect(swatch, QColor(*self._rgb))
        draw_frame(p, swatch, col("ink") if enabled else col("line"))
        red, green, blue = self._rgb
        p.setFont(font(12, 700))
        p.setPen(col("ink") if enabled else col("mute"))
        p.drawText(QRect(40, 0, 100, r.height()), int(Qt.AlignmentFlag.AlignVCenter), f"#{red:02X}{green:02X}{blue:02X}")
        p.setFont(font(10))
        p.setPen(col("mute"))
        p.drawText(
            QRect(0, 0, r.width() - 12, r.height()),
            int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight),
            f"RGB {red} {green} {blue}",
        )
        if self._kbd_focus and enabled:
            draw_focus(p, r)
        p.end()


class ThemeSwitch(KbdFocus, QWidget):
    """``ТЕМА [□ Светлая][■ Тёмная]`` segmented switch."""

    chosen = Signal(str)  # "light" | "dark"

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._dark = False
        self._hot = -1
        self.setFixedSize(2 + 2 * 84, 28)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def set_dark(self, dark: bool) -> None:
        self._dark = dark
        self.update()

    def _segment(self, index: int) -> QRect:
        return QRect(1 + index * 84, 1, 84, self.height() - 2)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        hot = 0 if self._segment(0).contains(event.position().toPoint()) else 1
        if hot != self._hot:
            self._hot = hot
            self.update()

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hot = -1
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.chosen.emit("light" if self._segment(0).contains(event.position().toPoint()) else "dark")

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Space, Qt.Key.Key_Return):
            self.chosen.emit("dark" if not self._dark else "light")
        else:
            super().keyPressEvent(event)

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        draw_frame(p, self.rect(), col("ink"))
        for index, (label, filled) in enumerate((("Светлая", False), ("Тёмная", True))):
            seg = self._segment(index)
            selected = self._dark == filled
            if selected:
                p.fillRect(seg, col("ink"))
            elif self._hot == index:
                p.fillRect(seg, col("hover"))
            fg = col("inv") if selected else col("ink")
            glyph = QRect(seg.left() + 10, seg.center().y() - 3, 7, 7)
            if filled:
                p.fillRect(glyph, fg)
            else:
                draw_frame(p, glyph, fg)
            p.setFont(font(11))
            p.setPen(fg)
            p.drawText(
                QRect(seg.left() + 23, seg.top(), seg.width() - 23, seg.height()),
                int(Qt.AlignmentFlag.AlignVCenter),
                label,
            )
        if self._kbd_focus:
            draw_focus(p, self.rect().adjusted(-1, -1, 1, 1))
        p.end()
