"""Side panel with the processing options."""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
)

from core.formats import OUTPUT_FORMATS, format_info
from core.options import Mode, ProcessingOptions, QualityLevel
from gui.settings import AppSettings

_MODE_LABELS = {
    Mode.COMPRESS: "Только сжатие",
    Mode.CONVERT: "Только конвертация",
    Mode.CONVERT_COMPRESS: "Конвертация + сжатие",
}
_MODE_HINTS = {
    Mode.COMPRESS: "Формат сохраняется, размер уменьшается без видимой потери качества. "
    "Если результат больше оригинала — файл остаётся как есть. HEIC сохраняется как JPEG.",
    Mode.CONVERT: "Смена формата с высоким качеством, без дополнительного сжатия.",
    Mode.CONVERT_COMPRESS: "Смена формата и оптимизация размера за один проход.",
}
_QUALITY_LABELS = {
    QualityLevel.MAXIMUM: "Максимальное качество",
    QualityLevel.BALANCED: "Баланс",
    QualityLevel.SMALLEST: "Минимальный размер",
}


def _section(text: str) -> QLabel:
    label = QLabel(text.upper())
    label.setObjectName("sectionTitle")
    return label


class SettingsPanel(QFrame):
    """Mode, output format, compression level, background colour, metadata and workers."""

    changed = Signal()

    def __init__(self, settings: AppSettings, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self.setFixedWidth(300)
        self._background = settings.background

        self._modes = QButtonGroup(self)
        mode_box = QVBoxLayout()
        self._mode_buttons: dict[Mode, QRadioButton] = {}
        for mode, label in _MODE_LABELS.items():
            button = QRadioButton(label)
            self._modes.addButton(button)
            self._mode_buttons[mode] = button
            mode_box.addWidget(button)
        self._mode_hint = QLabel()
        self._mode_hint.setWordWrap(True)
        self._mode_hint.setProperty("muted", True)

        self._format = QComboBox()
        for fmt in OUTPUT_FORMATS:
            self._format.addItem(format_info(fmt).label, fmt)

        self._quality = QSlider(Qt.Orientation.Horizontal)
        self._quality.setRange(int(QualityLevel.MAXIMUM), int(QualityLevel.SMALLEST))
        self._quality.setTickPosition(QSlider.TickPosition.TicksBelow)
        self._quality.setPageStep(1)
        self._quality_label = QLabel()
        self._quality_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._bg_button = QPushButton()
        self._bg_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._bg_button.setToolTip("Цвет, которым заменяется прозрачность при сохранении в JPEG и BMP")

        self._metadata = QCheckBox("Удалить метаданные")
        self._metadata.setToolTip(
            "Выключено — EXIF и цветовой профиль сохраняются там, где их поддерживает формат"
        )
        metadata_hint = QLabel("EXIF, GPS, данные камеры")
        metadata_hint.setProperty("muted", True)
        metadata_hint.setContentsMargins(26, 0, 0, 0)

        self._workers = QSpinBox()
        self._workers.setRange(1, (os.cpu_count() or 1) * 2)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)
        layout.addWidget(_section("Режим"))
        layout.addLayout(mode_box)
        layout.addWidget(self._mode_hint)
        layout.addSpacing(6)
        layout.addWidget(_section("Формат результата"))
        layout.addWidget(self._format)
        layout.addSpacing(6)
        layout.addWidget(_section("Уровень сжатия"))
        layout.addWidget(self._quality)
        layout.addWidget(self._quality_label)
        layout.addSpacing(6)
        layout.addWidget(_section("Фон вместо прозрачности"))
        layout.addWidget(self._bg_button)
        layout.addSpacing(6)
        layout.addWidget(self._metadata)
        layout.addWidget(metadata_hint)
        layout.addSpacing(6)
        row = QHBoxLayout()
        row.addWidget(_section("Потоков"))
        row.addStretch()
        row.addWidget(self._workers)
        layout.addLayout(row)
        layout.addStretch()

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

    # ------------------------------------------------------------------ internals

    def _on_changed(self, *_args) -> None:
        self._refresh()
        self.changed.emit()

    def _refresh(self) -> None:
        mode = self.mode()
        self._format.setEnabled(mode is not Mode.COMPRESS)
        self._quality.setEnabled(mode is not Mode.CONVERT)
        self._quality_label.setText(
            _QUALITY_LABELS[QualityLevel(self._quality.value())]
            if mode is not Mode.CONVERT
            else "Высокое качество (без сжатия)"
        )
        self._mode_hint.setText(_MODE_HINTS[mode])
        swatch = QPixmap(18, 18)
        swatch.fill(QColor(*self._background))
        self._bg_button.setIcon(swatch)
        r, g, b = self._background
        self._bg_button.setText(f"  #{r:02X}{g:02X}{b:02X}")

    def _pick_background(self) -> None:
        colour = QColorDialog.getColor(QColor(*self._background), self, "Цвет фона")
        if colour.isValid():
            self._background = (colour.red(), colour.green(), colour.blue())
            self._on_changed()

