"""The result summary shown above the list when a batch has finished."""
from __future__ import annotations

from PySide6.QtCore import QRect
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget

from core.models import Summary
from core.utils import format_duration, format_size
from gui.widgets.kit import ChipLabel, ElidedTx, Rule, Surface, Tx, col, hatch_brush


class _RatioBar(QWidget):
    """10 px bar: ink = what is left, hatched lime = what was saved."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(10)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._left = 1.0

    def set_ratio(self, left: float) -> None:
        self._left = min(1.0, max(0.0, left))
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        r = self.rect()
        p.fillRect(QRect(0, 0, r.width(), 1), col("line"))
        body = r.adjusted(0, 1, 0, 0)
        width = round(body.width() * self._left)
        p.fillRect(QRect(body.left(), body.top(), width, body.height()), col("ink"))
        p.fillRect(QRect(body.left() + width, body.top(), body.width() - width, body.height()), hatch_brush("lime"))
        p.end()


def _cell(title: str, value: QWidget) -> QWidget:
    cell = QWidget()
    layout = QVBoxLayout(cell)
    layout.setContentsMargins(14, 12, 14, 12)
    layout.setSpacing(6)
    layout.addWidget(ElidedTx(title, 10, tone="mute", spacing=0.08))
    layout.addStretch()
    layout.addWidget(value)
    return cell


class SummaryStrip(Surface):
    """``−78.3%`` big number plus saved / before→after / success / errors·time cells."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(None, bottom="ink", parent=parent)
        self._percent = Tx("", 44, 600, display=True)
        self._saved = ChipLabel("", "lime", px=14)
        self._sizes = ElidedTx("", 13, 700)
        self._ok = ElidedTx("", 14, 700)
        self._errors = ChipLabel("", "ink", px=12)
        self._time = Tx("", 14, 700)
        self._bar = _RatioBar()

        head = QWidget()
        head_layout = QVBoxLayout(head)
        head_layout.setContentsMargins(16, 12, 20, 12)
        head_layout.setSpacing(4)
        head_layout.addWidget(Tx("/ ИТОГ · SAVED", 10, tone="mute", spacing=0.1))
        head_layout.addWidget(self._percent)

        saved_wrap = QWidget()
        saved_layout = QHBoxLayout(saved_wrap)
        saved_layout.setContentsMargins(0, 0, 0, 0)
        saved_layout.addWidget(self._saved)
        saved_layout.addStretch()
        errors_wrap = QWidget()
        errors_layout = QHBoxLayout(errors_wrap)
        errors_layout.setContentsMargins(0, 0, 0, 0)
        errors_layout.setSpacing(6)
        errors_layout.addWidget(self._errors)
        errors_layout.addWidget(self._time)
        errors_layout.addStretch()

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addWidget(head)
        for title, widget in (
            ("СЭКОНОМЛЕНО", saved_wrap),
            ("ИСХОДНО → ИТОГ", self._sizes),
            ("УСПЕШНО", self._ok),
            ("ОШИБКИ · ВРЕМЯ", errors_wrap),
        ):
            row.addWidget(Rule(vertical=True))
            row.addWidget(_cell(title, widget), 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(row)
        layout.addWidget(self._bar)

    def set_summary(self, summary: Summary, elapsed: float) -> None:
        pct = summary.saved_percent
        self._percent.setText(f"−{pct:.1f}%" if pct >= 0 else f"+{abs(pct):.1f}%")
        self._saved.setText(format_size(max(0, summary.saved_bytes)))
        self._saved.updateGeometry()
        self._sizes.setText(f"{format_size(summary.size_before)} → {format_size(summary.size_after)}")
        self._ok.setText(f"{summary.ok + summary.already_optimized} / {summary.total}")
        self._errors.setText(f"{summary.errors:02d}")
        self._errors.updateGeometry()
        self._time.setText(f"· {format_duration(elapsed)}")
        self._bar.set_ratio(summary.size_after / summary.size_before if summary.size_before else 1.0)
