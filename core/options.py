"""User-facing processing options."""
from __future__ import annotations

import enum
import os
from dataclasses import dataclass, field

from core.formats import ImageFormat, format_info


class Mode(enum.Enum):
    """The three processing modes."""

    COMPRESS = "compress"  # keep the format, shrink the file
    CONVERT = "convert"  # change the format with high-quality settings
    CONVERT_COMPRESS = "convert_compress"  # change the format and optimise


class QualityLevel(enum.IntEnum):
    """Compression level slider positions."""

    MAXIMUM = 0  # maximum quality
    BALANCED = 1
    SMALLEST = 2  # smallest size


def default_workers() -> int:
    """Default size of the worker pool: the number of CPU cores."""
    return max(1, os.cpu_count() or 1)


@dataclass(frozen=True)
class ProcessingOptions:
    """Everything a worker needs to know about *how* to process an image."""

    mode: Mode = Mode.COMPRESS
    target_format: ImageFormat = ImageFormat.WEBP
    quality: QualityLevel = QualityLevel.BALANCED
    background: tuple[int, int, int] = (255, 255, 255)
    remove_metadata: bool = True
    workers: int = field(default_factory=default_workers)

    @property
    def compress(self) -> bool:
        """Whether the result should be optimised for size."""
        return self.mode in (Mode.COMPRESS, Mode.CONVERT_COMPRESS)

    @property
    def threads_per_worker(self) -> int:
        """Encoder threads each worker may use so the CPU is not oversubscribed."""
        return max(1, default_workers() // max(1, self.workers))

    def output_format_for(self, source: ImageFormat) -> ImageFormat:
        """Output format for a given input format.

        In compress-only mode the format is kept; formats that cannot be written
        (HEIC/HEIF) fall back to JPEG.
        """
        if self.mode is Mode.COMPRESS:
            return source if format_info(source).writable else ImageFormat.JPEG
        return self.target_format
