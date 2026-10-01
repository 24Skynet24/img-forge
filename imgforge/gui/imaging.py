"""Bridges between Pillow images and Qt images."""
from __future__ import annotations

from PIL import Image
from PySide6.QtGui import QImage


def pil_to_qimage(img: Image.Image) -> QImage:
    """Convert a Pillow image to a premultiplied-RGBA ``QImage`` that owns its memory."""
    premultiplied = img.convert("RGBa")
    qimage = QImage(
        premultiplied.tobytes(),
        premultiplied.width,
        premultiplied.height,
        premultiplied.width * 4,
        QImage.Format.Format_RGBA8888_Premultiplied,
    )
    return qimage.copy()  # detach from the temporary bytes buffer
