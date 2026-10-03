"""Small arrow icons for combo/spin boxes, generated at runtime (Qt style sheets need image files)."""
from __future__ import annotations

import tempfile
from pathlib import Path

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap

from gui.themes.tokens import Tokens


def _arrow(colour: str, up: bool, size: int = 20) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(colour), 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    m, mid, far = size * 0.28, size * 0.5, size * 0.72
    tip, base = (m + 1, far) if up else (far - 1, m)
    p.drawLine(QPointF(m, base), QPointF(mid, tip))
    p.drawLine(QPointF(mid, tip), QPointF(far, base))
    p.end()
    return pm


def arrow_icon_urls(tokens: Tokens) -> tuple[str, str]:
    """Write the (down, up) arrow PNGs for ``tokens`` and return QSS-ready file URLs."""
    folder = Path(tempfile.gettempdir()) / "imgforge-theme"
    folder.mkdir(parents=True, exist_ok=True)
    urls = []
    for name, up in (("down", False), ("up", True)):
        path = folder / f"arrow-{name}-{tokens.muted.lstrip('#')}.png"
        if not path.exists():
            _arrow(tokens.muted, up).save(str(path), "PNG")
        urls.append(path.as_posix())
    return urls[0], urls[1]
