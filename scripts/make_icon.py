"""Generate ``assets/icon.ico`` from the ImgForge mark (run once; the result is committed).

    python scripts/make_icon.py

The mark is a solid block that breaks apart into pixels (violet = the last pixel / output).
Large sizes use the detailed 24-unit mark, 16-32 px use the simplified 4-unit one, both drawn
with hard pixel edges on a square paper tile so the icon reads on light and dark taskbars.
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtGui import QGuiApplication, QPainter, QPixmap

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from gui.themes.mark import paint_icon  # noqa: E402

SIZES = (16, 24, 32, 48, 64, 128, 256)


def render(size: int) -> Image.Image:
    """One icon frame (the same painter the title bar uses)."""
    pm = QPixmap(size, size)
    p = QPainter(pm)
    paint_icon(p, size)
    p.end()
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    pm.save(buffer, "PNG")
    return Image.open(io.BytesIO(bytes(buffer.data()))).convert("RGBA")


def main() -> None:
    _app = QGuiApplication.instance() or QGuiApplication(sys.argv)  # Qt needs an application to paint pixmaps
    frames = {size: render(size) for size in SIZES}
    target = ROOT / "assets" / "icon.ico"
    target.parent.mkdir(exist_ok=True)
    largest = frames[max(SIZES)]
    largest.save(
        target,
        format="ICO",
        sizes=[(s, s) for s in SIZES],
        append_images=[frames[s] for s in SIZES if s != max(SIZES)],
    )
    print(f"wrote {target} with sizes {sorted(Image.open(target).info['sizes'])}")


if __name__ == "__main__":
    main()
