"""Qt style sheet and palette generated from colour tokens.

Most of the UI is custom-painted; the style sheet covers what is left to Qt: labels, menus,
tooltips, scroll bars, the combo popup and the stock dialogs (message box, colour picker).
Fonts are not set here: a style-sheet font would override the per-widget fonts.
"""
from __future__ import annotations

from string import Template

from PySide6.QtGui import QColor, QPalette

from gui.themes.tokens import Tokens

_QSS = Template(
    """
QMainWindow, QDialog, QMessageBox, QColorDialog { background: $bg; }
QLabel { background: transparent; color: $ink; }
QLabel[tone="mute"], QLabel[muted="true"] { color: $mute; }
QLabel[tone="vtext"] { color: $vtext; }
QLabel[tone="inv"] { color: $inv; }
QToolTip { background: $panel; color: $ink; border: 1px solid $ink; padding: 4px 6px; }

QPushButton {
    background: $panel; color: $ink; border: 1px solid $ink; border-radius: 0; padding: 6px 14px; min-height: 20px;
}
QPushButton:hover { background: $ink; color: $inv; }
QPushButton:default { border: 2px solid $violet; }
QPushButton:disabled { background: $line2; color: $mute; border-color: $line; }

QCheckBox { color: $ink; spacing: 8px; background: transparent; }
QCheckBox::indicator { width: 14px; height: 14px; border: 1px solid $ink; background: $panel; }
QCheckBox::indicator:checked { background: $ink; }

QMenu { background: $panel; color: $ink; border: 1px solid $ink; padding: 2px; }
QMenu::item { padding: 6px 24px 6px 14px; }
QMenu::item:selected { background: $ink; color: $inv; }
QMenu::item:disabled { color: $mute; }
QMenu::separator { height: 1px; background: $line; margin: 3px 0; }

QComboBox QAbstractItemView { background: $panel; border: 1px solid $ink; outline: none; padding: 0; }

QScrollArea { background: transparent; border: none; }
QScrollBar:vertical { background: $line2; width: 7px; margin: 0; border: none; }
QScrollBar::handle:vertical { background: $ink; min-height: 30px; }
QScrollBar:horizontal { background: $line2; height: 7px; margin: 0; border: none; }
QScrollBar::handle:horizontal { background: $ink; min-width: 30px; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

QTableView { background: transparent; border: none; outline: none; }
QAbstractItemView { selection-background-color: $hover; selection-color: $ink; }
QLineEdit, QSpinBox, QComboBox { background: $panel; color: $ink; border: 1px solid $ink; border-radius: 0; padding: 3px 6px; }
"""
)


def build_stylesheet(t: Tokens) -> str:
    """Render the application style sheet for the given tokens."""
    return _QSS.substitute(t.__dict__)


def build_palette(t: Tokens) -> QPalette:
    """A QPalette matching the tokens (for native-looking widgets the QSS does not cover)."""
    p = QPalette()
    roles = {
        QPalette.ColorRole.Window: t.bg,
        QPalette.ColorRole.WindowText: t.ink,
        QPalette.ColorRole.Base: t.panel,
        QPalette.ColorRole.AlternateBase: t.hover,
        QPalette.ColorRole.Text: t.ink,
        QPalette.ColorRole.Button: t.panel,
        QPalette.ColorRole.ButtonText: t.ink,
        QPalette.ColorRole.ToolTipBase: t.panel,
        QPalette.ColorRole.ToolTipText: t.ink,
        QPalette.ColorRole.Highlight: t.violet,
        QPalette.ColorRole.HighlightedText: "#FFFFFF",
        QPalette.ColorRole.PlaceholderText: t.mute,
        QPalette.ColorRole.Link: t.vtext,
        QPalette.ColorRole.BrightText: t.inv,
    }
    for role, colour in roles.items():
        p.setColor(role, QColor(colour))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.WindowText, QPalette.ColorRole.ButtonText):
        p.setColor(QPalette.ColorGroup.Disabled, role, QColor(t.mute))
    return p
