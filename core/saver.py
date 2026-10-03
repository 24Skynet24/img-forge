"""Copying processed files from the temporary working folder to the user's destination.

The output mirrors the input structure: a dropped folder ``Photos`` becomes
``<destination>/Photos/...`` with the same sub-folders, loose files land directly
in the destination.
"""
from __future__ import annotations

import enum
import os
import shutil
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePath


class ConflictAction(enum.Enum):
    """What to do when the destination already contains an item with the same name."""

    OVERWRITE = "overwrite"
    RENAME = "rename"
    SKIP = "skip"


@dataclass(frozen=True)
class SaveEntry:
    """A processed file in the working folder and where it goes (relative to the destination)."""

    work_path: Path
    relative: PurePath


@dataclass
class SaveReport:
    """Outcome of :func:`save_outputs`."""

    saved: int = 0
    skipped: int = 0
    renamed: int = 0
    errors: list[tuple[PurePath, str]] = field(default_factory=list)
    cancelled: bool = False


# Called with (existing path, is_folder). Must return the action to take.
ConflictResolver = Callable[[Path, bool], ConflictAction]


def _norm(path: Path) -> str:
    return os.path.normcase(str(path))


def unique_path(path: Path, taken: set[str] | None = None) -> Path:
    """First of ``name_1.ext``, ``name_2.ext``, ... that is neither on disk nor in ``taken``."""
    taken = taken or set()
    counter = 1
    while True:
        candidate = path.with_name(f"{path.stem}_{counter}{path.suffix}")
        if not candidate.exists() and _norm(candidate) not in taken:
            return candidate
        counter += 1


def save_outputs(
    entries: Sequence[SaveEntry],
    dest_root: Path,
    resolver: ConflictResolver,
    progress: Callable[[int, int], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> SaveReport:
    """Copy ``entries`` below ``dest_root``, asking ``resolver`` about name clashes.

    * A top-level folder that already exists is resolved once for the whole
      folder (overwrite = merge into it, rename = ``Photos_1``, skip = ignore it).
    * A loose file that already exists is resolved individually.
    * Clashes between queued items themselves (two ``a.jpg`` from different
      folders, ``a.png`` + ``a.jpg`` converted to WebP) are renamed silently.
    """
    report = SaveReport()
    dest_root.mkdir(parents=True, exist_ok=True)
    claimed: set[str] = set()
    folders: dict[str, Path | None] = {}
    total = len(entries)

    for done, entry in enumerate(entries, start=1):
        if cancelled is not None and cancelled():
            report.cancelled = True
            break
        parts = entry.relative.parts
        target: Path | None
        if len(parts) > 1:
            if parts[0] not in folders:
                folders[parts[0]] = _resolve_folder(dest_root / parts[0], resolver, report)
            base = folders[parts[0]]
            target = base.joinpath(*parts[1:]) if base is not None else None
        else:
            target = _resolve_file(dest_root / parts[0], claimed, resolver, report)

        if target is None:
            report.skipped += 1
        else:
            if _norm(target) in claimed:
                target = unique_path(target, claimed)
                report.renamed += 1
            claimed.add(_norm(target))
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(entry.work_path, target)
                report.saved += 1
            except OSError as exc:
                report.errors.append((entry.relative, str(exc)))
        if progress is not None:
            progress(done, total)
    return report


def _resolve_folder(path: Path, resolver: ConflictResolver, report: SaveReport) -> Path | None:
    if not path.exists():
        return path
    if path.is_dir():
        action = resolver(path, True)
    else:  # a file blocks the folder name
        action = ConflictAction.RENAME
    if action is ConflictAction.SKIP:
        return None
    if action is ConflictAction.OVERWRITE and path.is_dir():
        return path
    report.renamed += 1
    return unique_path(path)


def _resolve_file(
    path: Path, claimed: set[str], resolver: ConflictResolver, report: SaveReport
) -> Path | None:
    if not path.exists() or _norm(path) in claimed:
        return path
    action = resolver(path, path.is_dir()) if not path.is_dir() else ConflictAction.RENAME
    if action is ConflictAction.SKIP:
        return None
    if action is ConflictAction.OVERWRITE:
        return path
    report.renamed += 1
    return unique_path(path, claimed)
