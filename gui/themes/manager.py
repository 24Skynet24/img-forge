"""Applies the light/dark theme and follows the Windows colour scheme."""
from __future__ import annotations

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QApplication

from gui.themes.icons import arrow_icon_urls
from gui.themes.stylesheet import build_palette, build_stylesheet
from gui.themes.tokens import DARK, LIGHT, Tokens

SYSTEM, LIGHT_THEME, DARK_THEME = "system", "light", "dark"
PREFERENCES = (SYSTEM, LIGHT_THEME, DARK_THEME)


class ThemeManager(QObject):
    """Owns the theme preference ("system", "light" or "dark") and applies it app-wide."""

    changed = Signal(object)  # emits the active Tokens

    def __init__(self, app: QApplication, preference: str = SYSTEM) -> None:
        super().__init__(app)
        self._app = app
        self._preference = preference if preference in PREFERENCES else SYSTEM
        self._tokens: Tokens = LIGHT
        app.styleHints().colorSchemeChanged.connect(self._on_system_scheme_changed)

    @property
    def preference(self) -> str:
        return self._preference

    @property
    def tokens(self) -> Tokens:
        return self._tokens

    @property
    def is_dark(self) -> bool:
        return self._tokens is DARK

    def set_preference(self, preference: str) -> None:
        """Change the theme preference and re-apply it."""
        self._preference = preference if preference in PREFERENCES else SYSTEM
        self.apply()

    def apply(self) -> None:
        """Force the colour scheme (title bar included) and refresh palette + style sheet."""
        hints = self._app.styleHints()
        if self._preference == SYSTEM:
            hints.unsetColorScheme()
        else:
            hints.setColorScheme(
                Qt.ColorScheme.Dark if self._preference == DARK_THEME else Qt.ColorScheme.Light
            )
        self._apply_tokens()

    def _apply_tokens(self) -> None:
        if self._preference == SYSTEM:
            dark = self._app.styleHints().colorScheme() == Qt.ColorScheme.Dark
        else:  # explicit choice: do not depend on the platform honouring setColorScheme
            dark = self._preference == DARK_THEME
        tokens = DARK if dark else LIGHT
        self._tokens = tokens
        self._app.setPalette(build_palette(tokens))
        self._app.setStyleSheet(build_stylesheet(tokens, *arrow_icon_urls(tokens)))
        self.changed.emit(tokens)

    def _on_system_scheme_changed(self, _scheme: Qt.ColorScheme) -> None:
        if self._preference == SYSTEM:
            self._apply_tokens()
