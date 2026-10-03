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


def plural(n: int, forms: tuple[str, str, str]) -> str:
    """Russian plural form: ``plural(2, ("файл", "файла", "файлов")) == "файла"``."""
    if 11 <= n % 100 <= 14:
        return forms[2]
    if n % 10 == 1:
        return forms[0]
    return forms[1] if 2 <= n % 10 <= 4 else forms[2]


def format_duration(seconds: float) -> str:
    """``mm:ss`` or ``h:mm:ss``."""
    total = max(0, int(round(seconds)))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"
