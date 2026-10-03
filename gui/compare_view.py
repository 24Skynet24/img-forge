"""Before/after comparison: draggable split, synchronized zoom and pan, 100% pixel view."""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QImage,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPen,
    QPixmap,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.formats import format_info
from core.models import FileResult
from core.utils import format_size
from gui.themes.tokens import Tokens
from gui.workers import ImageLoadWorker

_GRAB = 12  # px around the split line that grab the handle
_MIN_ZOOM, _MAX_ZOOM = 0.01, 64.0


class _Pyramid:
    """An image plus lazily built half-size copies, for clean downscaled drawing."""

    def __init__(self, image: QImage) -> None:
        self.levels = [image]

    @property
    def base(self) -> QImage:
        return self.levels[0]

    def level_for(self, scale: float) -> QImage:
        """Smallest level that is still at least as large as the drawn size."""
        if scale >= 0.999:
            return self.levels[0]
        k = int(math.floor(math.log2(1.0 / scale)))
        while len(self.levels) <= k:
            prev = self.levels[-1]
            if prev.width() <= 1 or prev.height() <= 1:
                break
            self.levels.append(
                prev.scaled(
                    max(1, prev.width() // 2),
                    max(1, prev.height() // 2),
                    Qt.AspectRatioMode.IgnoreAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        return self.levels[min(k, len(self.levels) - 1)]


class CompareView(QWidget):
    """Original on the left of a vertical split line, result on the right.

    Mouse wheel zooms around the cursor, dragging pans (both images together),
    dragging the split line moves the divider.
    """

    zoomChanged = Signal(float)

    def __init__(self, tokens: Tokens, parent=None) -> None:
        super().__init__(parent)
        self._tokens = tokens
        self._original: _Pyramid | None = None
        self._result: _Pyramid | None = None
        self._zoom = 1.0
        self._offset = QPointF(0, 0)
        self._split = 0.5  # fraction of the widget width
        self._drag: str | None = None
        self._last = QPointF()
        self._has_alpha = False
        self._fitted = True
        self._checker: QPixmap | None = None
        self._labels = ("Оригинал", "Результат")
        self.setMouseTracking(True)
        self.setMinimumSize(480, 320)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    # ------------------------------------------------------------------ public

    def set_images(self, original: QImage, result: QImage) -> None:
        self._original = _Pyramid(original)
        self._result = _Pyramid(result)
        self._has_alpha = original.hasAlphaChannel() or result.hasAlphaChannel()
        self.fit()

    def set_tokens(self, tokens: Tokens) -> None:
        self._tokens = tokens
        self._checker = None
        self.update()

    @property
    def zoom(self) -> float:
        return self._zoom

    def fit(self) -> None:
        """Fit the whole image into the view."""
        self._fitted = True
        if self._original is None:
            return
        w, h = self._original.base.width(), self._original.base.height()
        zoom = min(self.width() / max(1, w), self.height() / max(1, h)) * 0.96
        self._set_zoom(min(max(zoom, _MIN_ZOOM), 16.0), keep_centre=False)
        self._centre()
        self.update()

    def actual_size(self) -> None:
        """100% view: one image pixel per screen pixel, centred."""
        self._fitted = False
        self._set_zoom(1.0 / self.devicePixelRatioF(), keep_centre=False)  # 1 image px = 1 device px
        self._centre()
        self.update()

    def reset_split(self) -> None:
        self._split = 0.5
        self.update()

    # ------------------------------------------------------------------ geometry

    def _centre(self) -> None:
        if self._original is None:
            return
        w = self._original.base.width() * self._zoom
        h = self._original.base.height() * self._zoom
        self._offset = QPointF((self.width() - w) / 2, (self.height() - h) / 2)

    def _set_zoom(self, zoom: float, *, keep_centre: bool, anchor: QPointF | None = None) -> None:
        zoom = min(max(zoom, _MIN_ZOOM), _MAX_ZOOM)
        if anchor is not None and zoom != self._zoom:
            ratio = zoom / self._zoom
            self._offset = anchor - (anchor - self._offset) * ratio
        self._zoom = zoom
        self.zoomChanged.emit(zoom * self.devicePixelRatioF())  # percent of physical pixels

    def _split_x(self) -> float:
        return self._split * self.width()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self._fitted:
            self.fit()

    # ------------------------------------------------------------------ interaction

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        if self._original is None:
            return
        steps = event.angleDelta().y() / 120.0
        if steps == 0:
            return
        self._fitted = False
        self._set_zoom(self._zoom * (1.25**steps), keep_centre=False, anchor=event.position())
        self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            return
        pos = event.position()
        self._last = pos
        self._drag = "split" if abs(pos.x() - self._split_x()) <= _GRAB else "pan"
        if self._drag == "split":
            self._move_split(pos.x())
        else:
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        pos = event.position()
        if self._drag == "split":
            self._move_split(pos.x())
        elif self._drag == "pan":
            self._offset += pos - self._last
            self._last = pos
            self._fitted = False
            self.update()
        else:
            near = abs(pos.x() - self._split_x()) <= _GRAB
            self.setCursor(Qt.CursorShape.SplitHCursor if near else Qt.CursorShape.OpenHandCursor)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._drag = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if abs(event.position().x() - self._split_x()) > _GRAB:
            self.fit()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_0, Qt.Key.Key_1):
            self.actual_size()
        elif event.key() in (Qt.Key.Key_F, Qt.Key.Key_9):
            self.fit()
        elif event.key() == Qt.Key.Key_Left:
            self._split = max(0.0, self._split - 0.05)
            self.update()
        elif event.key() == Qt.Key.Key_Right:
            self._split = min(1.0, self._split + 0.05)
            self.update()
        else:
            super().keyPressEvent(event)

    def _move_split(self, x: float) -> None:
        self._split = min(1.0, max(0.0, x / max(1, self.width())))
        self.update()

    # ------------------------------------------------------------------ painting

    def _checker_brush(self) -> QBrush:
        if self._checker is None:
            size = 8
            pm = QPixmap(size * 2, size * 2)
            pm.fill(QColor(self._tokens.checker_a))
            p = QPainter(pm)
            p.fillRect(0, 0, size, size, QColor(self._tokens.checker_b))
            p.fillRect(size, size, size, size, QColor(self._tokens.checker_b))
            p.end()
            self._checker = pm
        return QBrush(self._checker)

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(self._tokens.bg))
        if self._original is None or self._result is None:
            p.end()
            return
        base = self._original.base
        target = QRectF(
            self._offset.x(), self._offset.y(), base.width() * self._zoom, base.height() * self._zoom
        )
        visible = target.intersected(QRectF(self.rect()))
        if visible.isEmpty():
            p.end()
            return
        if self._has_alpha:
            p.fillRect(visible, self._checker_brush())
        split = self._split_x()
        for pyramid, clip in (
            (self._original, QRectF(0, 0, split, self.height())),
            (self._result, QRectF(split, 0, self.width() - split, self.height())),
        ):
            clipped = visible.intersected(clip)
            if clipped.isEmpty():
                continue
            self._draw(p, pyramid, target, clipped)
        self._draw_split(p, split)
        self._draw_badges(p, split)
        p.end()

    def _draw(self, p: QPainter, pyramid: _Pyramid, target: QRectF, area: QRectF) -> None:
        scale = target.width() / pyramid.base.width() * self.devicePixelRatioF()  # device px per image px
        level = pyramid.level_for(scale)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, scale < 0.999)
        fx = level.width() / target.width()
        fy = level.height() / target.height()
        source = QRectF(
            (area.x() - target.x()) * fx,
            (area.y() - target.y()) * fy,
            area.width() * fx,
            area.height() * fy,
        )
        p.drawImage(area, level, source)

    def _draw_split(self, p: QPainter, x: float) -> None:
        accent = QColor(self._tokens.accent)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setPen(QPen(QColor(0, 0, 0, 90), 3))
        p.drawLine(QPointF(x, 0), QPointF(x, self.height()))
        p.setPen(QPen(QColor("#ffffff"), 1.5))
        p.drawLine(QPointF(x, 0), QPointF(x, self.height()))
        cy = self.height() / 2
        p.setPen(QPen(QColor("#ffffff"), 2))
        p.setBrush(accent)
        p.drawEllipse(QPointF(x, cy), 15, 15)
        p.setPen(QPen(QColor("#ffffff"), 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        for sign in (-1, 1):  # two small arrows ◀ ▶
            tip = x + sign * 8
            p.drawLine(QPointF(tip, cy), QPointF(tip - sign * 4, cy - 4))
            p.drawLine(QPointF(tip, cy), QPointF(tip - sign * 4, cy + 4))

    def _draw_badges(self, p: QPainter, split: float) -> None:
        font = QFont(self.font())
        font.setBold(True)
        font.setPointSizeF(max(8.0, font.pointSizeF() - 1))
        p.setFont(font)
        metrics = p.fontMetrics()
        for text, left in ((self._labels[0], True), (self._labels[1], False)):
            w = metrics.horizontalAdvance(text) + 20
            h = metrics.height() + 10
            x = 12.0 if left else self.width() - w - 12.0
            if left and x + w > split - 6 or (not left and x < split + 6):
                continue  # not enough room next to the divider
            rect = QRectF(x, 12, w, h)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 150))
            p.drawRoundedRect(rect, h / 2, h / 2)
            p.setPen(QColor("#ffffff"))
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)


def _describe(name: str, size: int, dims: tuple[int, int] | None, fmt_label: str, extra: str = "") -> str:
    dims_text = f"{dims[0]}×{dims[1]}" if dims else "—"
    text = f"<b>{name}</b> · {format_size(size)} · {dims_text} · {fmt_label}"
    return text + (f" · {extra}" if extra else "")


class CompareDialog(QDialog):
    """Window with the :class:`CompareView` and the size/format summary of both versions."""

    def __init__(self, result: FileResult, tokens: Tokens, parent=None) -> None:
        super().__init__(parent)
        assert result.output_path is not None
        self.setWindowTitle(f"Сравнение — {result.source.name}")
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, True)
        self.resize(1100, 760)
        self._result = result
        self._view = CompareView(tokens)
        self._status = QLabel("Загрузка изображений…", alignment=Qt.AlignmentFlag.AlignCenter)
        self._status.setProperty("muted", True)

        src_fmt = format_info(result.source.format).label
        out_fmt = format_info(result.output_format).label if result.output_format else src_fmt
        saved = result.saved_percent
        change = f"−{saved:.1f}%" if saved >= 0 else f"+{abs(saved):.1f}%"
        left = QLabel(_describe("Оригинал", result.original_size, result.source_dims, src_fmt))
        right = QLabel(
            _describe("Результат", result.new_size, result.output_dims, out_fmt, f"<b>{change}</b>")
        )
        right.setAlignment(Qt.AlignmentFlag.AlignRight)
        info = QHBoxLayout()
        info.addWidget(left, 1)
        info.addWidget(right, 1)

        fit = QPushButton("По размеру окна")
        actual = QPushButton("100%")
        centre = QPushButton("Разделитель по центру")
        self._zoom_label = QLabel("100%")
        self._zoom_label.setMinimumWidth(56)
        close = QPushButton("Закрыть")
        fit.clicked.connect(self._view.fit)
        actual.clicked.connect(self._view.actual_size)
        centre.clicked.connect(self._view.reset_split)
        close.clicked.connect(self.close)
        self._view.zoomChanged.connect(lambda z: self._zoom_label.setText(f"{z * 100:.0f}%"))
        hint = QLabel("Колесо мыши — масштаб · перетаскивание — сдвиг · ползунок — граница до/после")
        hint.setProperty("muted", True)
        controls = QHBoxLayout()
        controls.addWidget(fit)
        controls.addWidget(actual)
        controls.addWidget(self._zoom_label)
        controls.addWidget(centre)
        controls.addStretch()
        controls.addWidget(close)

        layout = QVBoxLayout(self)
        layout.addLayout(info)
        layout.addWidget(self._view, 1)
        layout.addWidget(self._status)
        layout.addWidget(hint)
        layout.addLayout(controls)
        self._view.hide()

        self._worker = ImageLoadWorker(result.source.path, result.output_path, self)
        self._worker.loaded.connect(self._on_loaded)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def set_tokens(self, tokens: Tokens) -> None:
        self._view.set_tokens(tokens)

    def _on_loaded(self, original: QImage, result: QImage) -> None:
        self._status.hide()
        self._view.show()
        self._view.set_images(original, result)
        self._view.setFocus()

    def _on_failed(self, message: str) -> None:
        self._status.setText(f"Не удалось открыть изображения: {message}")

    def done(self, code: int) -> None:
        if self._worker.isRunning():
            self._worker.wait(5000)
        super().done(code)
