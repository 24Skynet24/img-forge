"""Small shared helpers."""
from __future__ import annotations

_UNITS = ("Б", "КБ", "МБ", "ГБ", "ТБ")


def format_size(size: float) -> str:
    """Human readable file size, e.g. ``1.25 МБ``."""
    value = float(size)
    sign = "-" if value < 0 else ""
    value = abs(value)
    for unit in _UNITS:
        if value < 1024 or unit == _UNITS[-1]:
            if unit == "Б":
                return f"{sign}{int(value)} {unit}"
            return f"{sign}{value:.2f} {unit}"
        value /= 1024
    return f"{sign}{value:.2f} {_UNITS[-1]}"  # pragma: no cover


def format_duration(seconds: float) -> str:
    """``mm:ss`` or ``h:mm:ss``."""
    total = max(0, int(round(seconds)))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"
