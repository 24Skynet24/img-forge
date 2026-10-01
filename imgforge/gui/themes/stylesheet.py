"""Qt style sheet and palette generated from colour tokens."""
from __future__ import annotations

from string import Template

from PySide6.QtGui import QColor, QPalette

from imgforge.gui.themes.tokens import Tokens

_QSS = Template(
    """
* { font-family: "Segoe UI", "Segoe UI Variable", sans-serif; font-size: 13px; }
QMainWindow, QDialog, QWidget#root { background: $bg; }
QLabel { background: transparent; color: $text; }
QLabel[muted="true"] { color: $muted; }
QLabel#brand { font-size: 18px; font-weight: 600; }
QLabel#sectionTitle { font-weight: 600; color: $muted; font-size: 11px; }
QLabel#summary { color: $text; }
QToolTip { background: $surface; color: $text; border: 1px solid $border; padding: 4px 6px; }

QFrame#card { background: $surface; border: 1px solid $border; border-radius: 12px; }
QFrame#card QLabel { background: transparent; }

QFrame#dropZone {
    background: $surface; border: 2px dashed $border; border-radius: 16px;
}
QFrame#dropZone[highlight="true"] { border-color: $accent; background: $surface_alt; }
QLabel#dropTitle { font-size: 22px; font-weight: 600; }

QPushButton {
    background: $surface_alt; color: $text; border: 1px solid $border;
    border-radius: 8px; padding: 7px 14px;
}
QPushButton:hover { border-color: $accent; }
QPushButton:pressed { background: $selection; }
QPushButton:disabled { color: $muted; background: $surface; border-color: $border; }
QPushButton#primary { background: $accent; color: $accent_text; border: 1px solid $accent; font-weight: 600; }
QPushButton#primary:hover { background: $accent_hover; border-color: $accent_hover; }
QPushButton#primary:disabled { background: $surface_alt; color: $muted; border-color: $border; }
QPushButton#danger { color: $danger; }
QToolButton {
    background: $surface_alt; color: $text; border: 1px solid $border;
    border-radius: 8px; padding: 6px 12px;
}
QToolButton:hover { border-color: $accent; }
QToolButton::menu-indicator { image: none; width: 0; }

QMenu { background: $surface; color: $text; border: 1px solid $border; padding: 4px; }
QMenu::item { padding: 6px 22px 6px 14px; border-radius: 6px; }
QMenu::item:selected { background: $selection; }
QMenu::item:disabled { color: $muted; }
QMenu::separator { height: 1px; background: $border; margin: 4px 6px; }

QCheckBox, QRadioButton { color: $text; spacing: 8px; background: transparent; }
QCheckBox:disabled, QRadioButton:disabled { color: $muted; }
QCheckBox::indicator, QRadioButton::indicator {
    width: 16px; height: 16px; border: 1px solid $border; background: $surface_alt;
}
QCheckBox::indicator { border-radius: 4px; }
QRadioButton::indicator { border-radius: 9px; }
QCheckBox::indicator:checked { background: $accent; border-color: $accent; }
QRadioButton::indicator:checked {
    border-color: $accent;
    background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5,
                                stop:0 $accent, stop:0.5 $accent, stop:0.56 $surface_alt, stop:1 $surface_alt);
}
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled { background: $surface; }

QComboBox, QSpinBox {
    background: $surface_alt; color: $text; border: 1px solid $border;
    border-radius: 8px; padding: 5px 10px; min-height: 20px;
}
QComboBox:hover, QSpinBox:hover { border-color: $accent; }
QComboBox:disabled, QSpinBox:disabled { color: $muted; background: $surface; }
QComboBox::drop-down { border: none; width: 26px; }
QComboBox::down-arrow { image: url($arrow_down); width: 14px; height: 14px; }
QSpinBox::up-button { subcontrol-origin: border; subcontrol-position: top right; width: 22px; border: none; background: transparent; }
QSpinBox::down-button { subcontrol-origin: border; subcontrol-position: bottom right; width: 22px; border: none; background: transparent; }
QSpinBox::up-arrow { image: url($arrow_up); width: 12px; height: 12px; }
QSpinBox::down-arrow { image: url($arrow_down); width: 12px; height: 12px; }
QComboBox QAbstractItemView {
    background: $surface; color: $text; border: 1px solid $border;
    selection-background-color: $selection; selection-color: $text; outline: none;
}

QSlider::groove:horizontal { height: 6px; background: $surface_alt; border: 1px solid $border; border-radius: 4px; }
QSlider::sub-page:horizontal { background: $accent; border-radius: 4px; }
QSlider::handle:horizontal {
    background: $accent; width: 16px; height: 16px; margin: -6px 0; border-radius: 9px;
    border: 2px solid $surface;
}
QSlider:disabled::sub-page:horizontal { background: $border; }
QSlider:disabled::handle:horizontal { background: $border; }

QProgressBar {
    background: $surface_alt; border: 1px solid $border; border-radius: 8px;
    text-align: center; color: $text; min-height: 18px;
}
QProgressBar::chunk { background: $accent; border-radius: 7px; }

QTableView {
    background: $surface; alternate-background-color: $surface_alt; color: $text;
    border: 1px solid $border; border-radius: 12px; gridline-color: transparent;
    selection-background-color: $selection; selection-color: $text; outline: none;
}
QTableView::item { padding: 0 8px; border: none; }
QHeaderView { background: transparent; }
QHeaderView::section {
    background: $surface; color: $muted; border: none; border-bottom: 1px solid $border;
    padding: 8px; font-weight: 600; font-size: 11px;
}
QTableCornerButton::section { background: $surface; border: none; }

QScrollBar:vertical { background: transparent; width: 12px; margin: 2px; }
QScrollBar::handle:vertical { background: $border; border-radius: 4px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: $muted; }
QScrollBar:horizontal { background: transparent; height: 12px; margin: 2px; }
QScrollBar::handle:horizontal { background: $border; border-radius: 4px; min-width: 30px; }
QScrollBar::handle:horizontal:hover { background: $muted; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

QMessageBox { background: $bg; }
"""
)


def build_stylesheet(t: Tokens, arrow_down: str, arrow_up: str) -> str:
    """Render the application style sheet for the given tokens and arrow icon URLs."""
    return _QSS.substitute(t.__dict__, arrow_down=arrow_down, arrow_up=arrow_up)


def build_palette(t: Tokens) -> QPalette:
    """A QPalette matching the tokens (for native-looking widgets the QSS does not cover)."""
    p = QPalette()
    roles = {
        QPalette.ColorRole.Window: t.bg,
        QPalette.ColorRole.WindowText: t.text,
        QPalette.ColorRole.Base: t.surface,
        QPalette.ColorRole.AlternateBase: t.surface_alt,
        QPalette.ColorRole.Text: t.text,
        QPalette.ColorRole.Button: t.surface_alt,
        QPalette.ColorRole.ButtonText: t.text,
        QPalette.ColorRole.ToolTipBase: t.surface,
        QPalette.ColorRole.ToolTipText: t.text,
        QPalette.ColorRole.Highlight: t.accent,
        QPalette.ColorRole.HighlightedText: t.accent_text,
        QPalette.ColorRole.PlaceholderText: t.muted,
        QPalette.ColorRole.Link: t.accent,
        QPalette.ColorRole.BrightText: t.accent_text,
    }
    for role, colour in roles.items():
        p.setColor(role, QColor(colour))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.WindowText, QPalette.ColorRole.ButtonText):
        p.setColor(QPalette.ColorGroup.Disabled, role, QColor(t.muted))
    return p
