"""Persistent user settings (QSettings, stored in the Windows registry)."""
from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtCore import QByteArray, QSettings

from imgforge.core.formats import OUTPUT_FORMATS, ImageFormat
from imgforge.core.options import Mode, ProcessingOptions, QualityLevel, default_workers
from imgforge.gui.themes.manager import PREFERENCES, SYSTEM


@dataclass
class AppSettings:
    """Settings remembered between launches."""

    mode: Mode = Mode.COMPRESS
    target_format: ImageFormat = ImageFormat.WEBP
    quality: QualityLevel = QualityLevel.BALANCED
    background: tuple[int, int, int] = (255, 255, 255)
    remove_metadata: bool = True
    workers: int = field(default_factory=default_workers)
    theme: str = SYSTEM
    last_dir: str = ""
    geometry: QByteArray | None = None

    @staticmethod
    def _store() -> QSettings:
        return QSettings("ImgForge", "ImgForge")

    @classmethod
    def load(cls) -> AppSettings:
        """Read settings, falling back to defaults for anything missing or invalid."""
        s = cls._store()
        out = cls()
        try:
            out.mode = Mode(str(s.value("mode", out.mode.value)))
        except ValueError:
            pass
        try:
            fmt = ImageFormat(str(s.value("target_format", out.target_format.value)))
            if fmt in OUTPUT_FORMATS:
                out.target_format = fmt
        except ValueError:
            pass
        try:
            out.quality = QualityLevel(int(s.value("quality", int(out.quality))))
        except (ValueError, TypeError):
            pass
        try:
            r, g, b = (int(c) for c in str(s.value("background", "255,255,255")).split(","))
            out.background = (r & 255, g & 255, b & 255)
        except ValueError:
            pass
        out.remove_metadata = bool(s.value("remove_metadata", out.remove_metadata, type=bool))
        try:
            out.workers = max(1, min(64, int(s.value("workers", out.workers))))
        except (ValueError, TypeError):
            pass
        theme = str(s.value("theme", SYSTEM))
        out.theme = theme if theme in PREFERENCES else SYSTEM
        out.last_dir = str(s.value("last_dir", ""))
        geometry = s.value("geometry")
        out.geometry = geometry if isinstance(geometry, QByteArray) else None
        return out

    def save(self) -> None:
        """Write all settings."""
        s = self._store()
        s.setValue("mode", self.mode.value)
        s.setValue("target_format", self.target_format.value)
        s.setValue("quality", int(self.quality))
        s.setValue("background", ",".join(str(c) for c in self.background))
        s.setValue("remove_metadata", self.remove_metadata)
        s.setValue("workers", self.workers)
        s.setValue("theme", self.theme)
        s.setValue("last_dir", self.last_dir)
        if self.geometry is not None:
            s.setValue("geometry", self.geometry)
        s.sync()

    def update_from(self, options: ProcessingOptions) -> None:
        """Copy the processing options chosen in the UI."""
        self.mode = options.mode
        self.target_format = options.target_format
        self.quality = options.quality
        self.background = options.background
        self.remove_metadata = options.remove_metadata
        self.workers = options.workers
