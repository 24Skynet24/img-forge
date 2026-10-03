"""Mode (/02) and parameters (/03) of the side panel."""
from __future__ import annotations

import os

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QButtonGroup, QColorDialog, QHBoxLayout, QVBoxLayout, QWidget

from core.formats import OUTPUT_FORMATS, format_info
from core.options import Mode, ProcessingOptions, QualityLevel
from gui.settings import AppSettings
from gui.widgets.controls import ColorField, FormatCombo, MetaCheck, ModeButton, StepSlider, Stepper
from gui.widgets.kit import Surface, Tx

_MODE_LABELS = {
    Mode.COMPRESS: "Только сжатие",
    Mode.CONVERT: "Только конвертация",
    Mode.CONVERT_COMPRESS: "Конвертация + сжатие",
}
_MODE_CODES = {Mode.COMPRESS: "CMP", Mode.CONVERT: "CNV", Mode.CONVERT_COMPRESS: "CNV+CMP"}
_MODE_HINTS = {
    Mode.COMPRESS: "Формат сохраняется, размер уменьшается без видимой потери качества. "
    "Если результат больше оригинала — файл остаётся как есть. HEIC сохраняется как JPEG.",
    Mode.CONVERT: "Смена формата с высоким качеством, без дополнительного сжатия.",
    Mode.CONVERT_COMPRESS: "Смена формата и оптимизация размера за один проход.",
}
_QUALITY_LABELS = {
    QualityLevel.MAXIMUM: "Макс. качество",
    QualityLevel.BALANCED: "Баланс",
    QualityLevel.SMALLEST: "Мин. размер",
}


def _field_head(title: str) -> tuple[QWidget, Tx]:
    """``ЗАГОЛОВОК ........ note`` row above a control; returns the row and the note label."""
    row = QWidget()
    note = Tx("", 10, tone="mute", spacing=0.08)
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(Tx(title, 10, tone="mute", spacing=0.08, upper=True))
    layout.addStretch()
    layout.addWidget(note)
    return row, note


class SettingsPanel(QWidget):
    """Mode, output format, compression level, background colour, metadata and workers."""

    changed = Signal()

    def __init__(self, settings: AppSettings, parent=None) -> None:
        super().__init__(parent)
        self._background = settings.background

        # ---- /02 mode
        self._modes = QButtonGroup(self)
        self._mode_buttons: dict[Mode, ModeButton] = {}
        mode_box = QVBoxLayout()
        mode_box.setSpacing(-1)  # neighbouring rows share one border line
        for mode, label in _MODE_LABELS.items():
            button = ModeButton(label, _MODE_CODES[mode])
            self._modes.addButton(button)
            self._mode_buttons[mode] = button
            mode_box.addWidget(button)
        self._lock_note = Tx("", 10, tone="mute", spacing=0.06)
        self._mode_hint = Tx("", 11, tone="mute")
        self._mode_hint.setWordWrap(True)

        mode_head = QHBoxLayout()
        mode_head.setSpacing(10)
        mode_head.addWidget(Tx("/02", 12, 700, "vtext"))
        mode_head.addWidget(Tx("РЕЖИМ", 12, 700, spacing=0.08))
        mode_head.addStretch()
        mode_head.addWidget(self._lock_note)

        mode_block = Surface(None, bottom="line")
        mode_layout = QVBoxLayout(mode_block)
        mode_layout.setContentsMargins(20, 14, 20, 16)
        mode_layout.setSpacing(0)
        mode_layout.addLayout(mode_head)
        mode_layout.addSpacing(12)
        mode_layout.addLayout(mode_box)
        mode_layout.addSpacing(10)
        mode_layout.addWidget(self._mode_hint)

        # ---- /03 parameters
        self._format = FormatCombo()
        for fmt in OUTPUT_FORMATS:
            info = format_info(fmt)
            details = [info.extension]
            if info.alpha:
                details.append("альфа")
            if info.animation:
                details.append("анимация")
            self._format.add_format(info.label, fmt, info.extension, " · ".join(details))
        fmt_head, self._format_note = _field_head("Формат результата")

        self._quality = StepSlider()
        self._quality.setRange(int(QualityLevel.MAXIMUM), int(QualityLevel.SMALLEST))
        self._quality_name = Tx("", 20, 600, display=True, spacing=0.02, upper=True)
        quality_head, self._quality_note = _field_head("Уровень сжатия")
        quality_scale = QWidget()
        scale = QHBoxLayout(quality_scale)
        scale.setContentsMargins(0, 0, 0, 0)
        scale.addWidget(Tx("← КАЧЕСТВО", 10, tone="mute", spacing=0.08))
        scale.addStretch()
        scale.addWidget(Tx("РАЗМЕР →", 10, tone="mute", spacing=0.08))

        self._bg_button = ColorField()
        self._bg_button.setToolTip("Цвет, которым заменяется прозрачность при сохранении в JPEG и BMP")

        self._metadata = MetaCheck("Удалить метаданные", "EXIF, GPS, данные камеры")
        self._metadata.setToolTip(
            "Выключено — EXIF и цветовой профиль сохраняются там, где их поддерживает формат"
        )

        self._workers = Stepper()
        self._workers.setRange(1, (os.cpu_count() or 1) * 2)

        params = QWidget()
        box = QVBoxLayout(params)
        box.setContentsMargins(20, 12, 20, 14)
        box.setSpacing(13)
        title = QHBoxLayout()
        title.setSpacing(10)
        title.addWidget(Tx("/03", 12, 700, "vtext"))
        title.addWidget(Tx("ПАРАМЕТРЫ", 12, 700, spacing=0.08))
        title.addStretch()
        box.addLayout(title)

        def field(*widgets: QWidget) -> QVBoxLayout:
            col = QVBoxLayout()
            col.setSpacing(6)
            for w in widgets:
                col.addWidget(w)
            return col

        box.addLayout(field(fmt_head, self._format))
        box.addLayout(field(quality_head, self._quality_name, self._quality, quality_scale))
        bg_head, _ = _field_head("Фон вместо прозрачности")
        box.addLayout(field(bg_head, self._bg_button))
        box.addWidget(self._metadata)
        threads = QHBoxLayout()
        threads.addWidget(Tx("Потоков", 10, tone="mute", spacing=0.08, upper=True))
        threads.addStretch()
        threads.addWidget(self._workers)
        box.addLayout(threads)
        box.addStretch()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(mode_block)
        layout.addWidget(params, 1)

        self.set_options(settings)
        self._modes.buttonToggled.connect(self._on_changed)
        self._format.currentIndexChanged.connect(self._on_changed)
        self._quality.valueChanged.connect(self._on_changed)
        self._metadata.toggled.connect(self._on_changed)
        self._workers.valueChanged.connect(self._on_changed)
        self._bg_button.clicked.connect(self._pick_background)

    # ------------------------------------------------------------------ public

    def options(self) -> ProcessingOptions:
        """The options currently selected in the panel."""
        return ProcessingOptions(
            mode=self.mode(),
            target_format=self._format.currentData(),
            quality=QualityLevel(self._quality.value()),
            background=self._background,
            remove_metadata=self._metadata.isChecked(),
            workers=self._workers.value(),
        )

    def mode(self) -> Mode:
        for mode, button in self._mode_buttons.items():
            if button.isChecked():
                return mode
        return Mode.COMPRESS

    def set_options(self, settings: AppSettings) -> None:
        """Load the remembered settings into the controls."""
        self._mode_buttons[settings.mode].setChecked(True)
        self._format.setCurrentIndex(max(0, self._format.findData(settings.target_format)))
        self._quality.setValue(int(settings.quality))
        self._metadata.setChecked(settings.remove_metadata)
        self._workers.setValue(settings.workers)
        self._background = settings.background
        self._refresh()

    def set_locked(self, locked: bool) -> None:
        """Disable editing while a batch is running."""
        self.setEnabled(not locked)
        self._lock_note.setText("■ ЗАБЛОКИРОВАНО" if locked else "")

    # ------------------------------------------------------------------ internals

    def _on_changed(self, *_args) -> None:
        self._refresh()
        self.changed.emit()

    def _refresh(self) -> None:
        mode = self.mode()
        self._format.setEnabled(mode is not Mode.COMPRESS)
        self._quality.setEnabled(mode is not Mode.CONVERT)
        self._format_note.setText("НЕДОСТУПНО · CMP" if mode is Mode.COMPRESS else "")
        if mode is Mode.CONVERT:
            self._quality_name.setText("Без сжатия")
            self._quality_note.setText("НЕДОСТУПНО · CNV")
        else:
            level = QualityLevel(self._quality.value())
            self._quality_name.setText(_QUALITY_LABELS[level])
            self._quality_note.setText(f"{int(level) + 1} / {len(QualityLevel)}")
        self._mode_hint.setText(_MODE_HINTS[mode])
        self._bg_button.set_rgb(self._background)

    def _pick_background(self) -> None:
        colour = QColorDialog.getColor(QColor(*self._background), self, "Цвет фона")
        if colour.isValid():
            self._background = (colour.red(), colour.green(), colour.blue())
            self._on_changed()
