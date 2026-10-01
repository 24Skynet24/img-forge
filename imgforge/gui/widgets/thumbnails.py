"""Lazy, cached thumbnail loading for the queue table."""
from __future__ import annotations

from collections import OrderedDict
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal
from PySide6.QtGui import QImage, QPixmap

from imgforge.core.preview import load_thumbnail
from imgforge.gui.imaging import pil_to_qimage

_DEVICE_PIXEL_RATIO = 2  # thumbnails are rendered at 2x for crisp HiDPI display


class _Signals(QObject):
    done = Signal(str, object)  # path, QImage | None


class _ThumbnailTask(QRunnable):
    def __init__(self, path: str, size: int, signals: _Signals) -> None:
        super().__init__()
        self._path = path
        self._size = size
        self._signals = signals

    def run(self) -> None:
        try:
            image: QImage | None = pil_to_qimage(load_thumbnail(Path(self._path), self._size))
        except Exception:  # noqa: BLE001 - unreadable files simply get no thumbnail
            image = None
        self._signals.done.emit(self._path, image)


class ThumbnailCache(QObject):
    """Loads thumbnails on demand (only for rows that are actually painted).

    ``pixmap`` returns immediately: the cached pixmap, or ``None`` while it is
    being loaded in the background, after which ``ready`` is emitted.
    """

    ready = Signal()

    def __init__(self, logical_size: int = 56, capacity: int = 3000, parent=None) -> None:
        super().__init__(parent)
        self._size = logical_size * _DEVICE_PIXEL_RATIO
        self._capacity = capacity
        self._cache: OrderedDict[str, QPixmap] = OrderedDict()
        self._pending: set[str] = set()
        self._failed: set[str] = set()
        self._priority = 0
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(3)
        self._signals = _Signals(self)
        self._signals.done.connect(self._on_done)

    def pixmap(self, path: str) -> QPixmap | None:
        cached = self._cache.get(path)
        if cached is not None:
            self._cache.move_to_end(path)
            return cached
        if path not in self._pending and path not in self._failed:
            self._pending.add(path)
            self._priority += 1  # newest request first: the user scrolled there
            self._pool.start(_ThumbnailTask(path, self._size, self._signals), self._priority)
        return None

    def forget(self, path: str) -> None:
        """Drop a cached thumbnail (e.g. when its row is removed)."""
        self._cache.pop(path, None)
        self._failed.discard(path)

    def clear(self) -> None:
        self._cache.clear()
        self._failed.clear()

    def _on_done(self, path: str, image: object) -> None:
        self._pending.discard(path)
        if image is None:
            self._failed.add(path)
            return
        pixmap = QPixmap.fromImage(image)  # type: ignore[arg-type]
        pixmap.setDevicePixelRatio(_DEVICE_PIXEL_RATIO)
        self._cache[path] = pixmap
        while len(self._cache) > self._capacity:
            self._cache.popitem(last=False)
        self.ready.emit()
