"""Plain data objects shared between the scanner, the pipeline and the GUI."""
from __future__ import annotations

import enum
from dataclasses import dataclass
from pathlib import Path, PurePath

from imgforge.core.formats import ImageFormat


class Status(enum.Enum):
    """Outcome of processing one file."""

    OK = "ok"
    ALREADY_OPTIMIZED = "already_optimized"
    ERROR = "error"


STATUS_LABELS: dict[Status, str] = {
    Status.OK: "OK",
    Status.ALREADY_OPTIMIZED: "Уже оптимизировано",
    Status.ERROR: "Ошибка",
}


@dataclass(frozen=True)
class SourceItem:
    """An image queued for processing.

    ``relative`` is the path of the item relative to the folder the user chooses
    when saving. For files found inside a dropped folder it starts with that
    folder's name; loose files consist of just the file name.
    """

    path: Path
    relative: PurePath
    format: ImageFormat
    size: int

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def folder(self) -> str:
        """Folder part of ``relative`` ("" for loose files)."""
        parent = self.relative.parent
        return "" if str(parent) in ("", ".") else str(parent)


@dataclass(frozen=True)
class FileResult:
    """Result of processing one :class:`SourceItem`."""

    index: int
    status: Status
    source: SourceItem
    output_path: Path | None = None
    relative_output: PurePath | None = None
    original_size: int = 0
    new_size: int = 0
    source_dims: tuple[int, int] | None = None
    output_dims: tuple[int, int] | None = None
    output_format: ImageFormat | None = None
    message: str = ""
    warnings: tuple[str, ...] = ()
    elapsed: float = 0.0

    @property
    def ok(self) -> bool:
        """True when an output file exists (processed or copied unchanged)."""
        return self.status is not Status.ERROR

    @property
    def saved_bytes(self) -> int:
        return self.original_size - self.new_size

    @property
    def saved_percent(self) -> float:
        if self.original_size <= 0:
            return 0.0
        return 100.0 * self.saved_bytes / self.original_size


@dataclass(frozen=True)
class Summary:
    """Aggregated statistics over a batch of results."""

    total: int
    ok: int
    already_optimized: int
    errors: int
    size_before: int
    size_after: int

    @property
    def saved_bytes(self) -> int:
        return self.size_before - self.size_after

    @property
    def saved_percent(self) -> float:
        return 100.0 * self.saved_bytes / self.size_before if self.size_before > 0 else 0.0


def summarize(results: list[FileResult]) -> Summary:
    """Aggregate ``results`` (errors do not count towards the sizes)."""
    good = [r for r in results if r.ok]
    return Summary(
        total=len(results),
        ok=sum(1 for r in results if r.status is Status.OK),
        already_optimized=sum(1 for r in results if r.status is Status.ALREADY_OPTIMIZED),
        errors=sum(1 for r in results if r.status is Status.ERROR),
        size_before=sum(r.original_size for r in good),
        size_after=sum(r.new_size for r in good),
    )
