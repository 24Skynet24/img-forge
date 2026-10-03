"""Colour tokens for the light and dark themes (cyber-brutalist: ink, paper, violet, lime)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Tokens:
    """A complete colour set; every widget colour in the app comes from here.

    ``ink``/``inv`` are the foreground and its inverse, ``violet`` marks activity and focus,
    ``lime`` marks a result. Errors deliberately have no red: they use hatching and an inverted chip.
    """

    bg: str
    panel: str
    ink: str
    inv: str
    mute: str
    line: str
    line2: str
    hover: str
    violet: str
    vtext: str  # violet that is readable as text on this theme
    lime: str
    onlime: str

    @property
    def checker_a(self) -> str:
        return self.panel

    @property
    def checker_b(self) -> str:
        return self.line


LIGHT = Tokens(
    bg="#EDEDE9",
    panel="#F7F7F4",
    ink="#0D0D0D",
    inv="#F7F7F4",
    mute="#5F5F5A",
    line="#C9C9C3",
    line2="#E0E0DB",
    hover="#E5E5E0",
    violet="#8A5CF6",
    vtext="#6A3BDE",
    lime="#D4FF3A",
    onlime="#0D0D0D",
)

DARK = Tokens(
    bg="#0B0B0C",
    panel="#131315",
    ink="#ECECE8",
    inv="#0B0B0C",
    mute="#8F8F8A",
    line="#36363B",
    line2="#202024",
    hover="#1D1D21",
    violet="#8A5CF6",
    vtext="#A98BFF",
    lime="#D4FF3A",
    onlime="#0D0D0D",
)

_current: Tokens = LIGHT


def current() -> Tokens:
    """The tokens of the active theme (read by every custom-painted widget)."""
    return _current


def set_current(tokens: Tokens) -> None:
    """Called by the theme manager before it re-applies the style sheet."""
    global _current
    _current = tokens
