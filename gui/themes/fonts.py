"""Bundled fonts: JetBrains Mono for the UI, Oswald for display text (both have Cyrillic)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PySide6.QtGui import QFont, QFontDatabase

MONO_FALLBACK = "Consolas"
_mono = MONO_FALLBACK
_display = "Impact"

_FILES = (
    "JetBrainsMono-Regular.ttf",
    "JetBrainsMono-Medium.ttf",
    "JetBrainsMono-Bold.ttf",
    "Oswald-SemiBold.ttf",
)


def load_fonts(folder: Path) -> bool:
    """Register the bundled fonts with Qt; returns False when they are missing."""
    global _mono, _display
    families: dict[str, list[str]] = {}
    for name in _FILES:
        path = folder / name
        if not path.exists():
            continue
        font_id = QFontDatabase.addApplicationFont(str(path))
        if font_id >= 0:
            families[name.split("-")[0]] = QFontDatabase.applicationFontFamilies(font_id)
    if families.get("JetBrainsMono"):
        _mono = families["JetBrainsMono"][0]
    if families.get("Oswald"):
        _display = families["Oswald"][0]
    font.cache_clear()
    return bool(families)


@lru_cache(maxsize=256)
def font(px: int = 12, weight: int = 400, *, display: bool = False, spacing: float = 0.0) -> QFont:
    """A pixel-sized UI font. ``spacing`` is letter spacing in em (CSS ``letter-spacing``)."""
    f = QFont(_display if display else _mono)
    f.setPixelSize(px)
    f.setWeight(QFont.Weight(weight))
    f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    if spacing:
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing * px)
    return f


def app_font() -> QFont:
    """The default font of the whole application."""
    return font(12)
