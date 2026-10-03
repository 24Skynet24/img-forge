"""Colour tokens for the light and dark themes."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Tokens:
    """A complete colour set; every widget colour in the app comes from here."""

    bg: str
    surface: str
    surface_alt: str
    border: str
    text: str
    muted: str
    accent: str
    accent_hover: str
    accent_text: str
    selection: str
    danger: str
    success: str
    warning: str
    checker_a: str
    checker_b: str


DARK = Tokens(
    bg="#14161a",
    surface="#1c1f25",
    surface_alt="#252932",
    border="#323843",
    text="#e7e9ee",
    muted="#98a0ad",
    accent="#4f8cff",
    accent_hover="#6c9fff",
    accent_text="#ffffff",
    selection="#2b4170",
    danger="#ff7070",
    success="#4cc38a",
    warning="#e5a93d",
    checker_a="#2a2d34",
    checker_b="#383c45",
)

LIGHT = Tokens(
    bg="#f3f4f7",
    surface="#ffffff",
    surface_alt="#eef0f4",
    border="#d7dce3",
    text="#1b2028",
    muted="#667085",
    accent="#2563eb",
    accent_hover="#1d4fd8",
    accent_text="#ffffff",
    selection="#d9e5ff",
    danger="#d02b38",
    success="#15894f",
    warning="#a8690f",
    checker_a="#ffffff",
    checker_b="#dfe3ea",
)
