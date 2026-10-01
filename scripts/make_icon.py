"""Generate ``assets/icon.ico`` (run once; the result is committed).

    python scripts/make_icon.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


def draw(size: int = 512) -> Image.Image:
    """A rounded blue tile with a white 'image' glyph."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # Vertical gradient inside a rounded square.
    gradient = Image.new("RGBA", (size, size))
    gd = ImageDraw.Draw(gradient)
    top, bottom = (79, 140, 255), (37, 83, 214)
    for y in range(size):
        t = y / (size - 1)
        gd.line([(0, y), (size, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)) + (255,))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1], radius=size // 5, fill=255)
    img.paste(gradient, (0, 0), mask)

    s = size / 512
    white = (255, 255, 255, 255)
    d.rounded_rectangle([96 * s, 128 * s, 416 * s, 384 * s], radius=36 * s, outline=white, width=int(26 * s))
    d.ellipse([300 * s, 176 * s, 356 * s, 232 * s], fill=white)
    d.line(
        [(120 * s, 360 * s), (214 * s, 248 * s), (270 * s, 312 * s), (320 * s, 270 * s), (392 * s, 360 * s)],
        fill=white, width=int(26 * s), joint="curve",
    )
    return img


if __name__ == "__main__":
    target = Path(__file__).resolve().parent.parent / "assets" / "icon.ico"
    target.parent.mkdir(exist_ok=True)
    draw().save(target, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(f"wrote {target}")
