"""Finding images in files and (nested) folders."""
from __future__ import annotations

import os
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path, PurePath

from imgforge.core.formats import format_from_path
from imgforge.core.models import SourceItem


@dataclass
class ScanResult:
    """Outcome of :func:`scan_paths`."""

    items: list[SourceItem] = field(default_factory=list)
    skipped: int = 0  # files that are not supported images
    duplicates: int = 0  # images that were already queued/scanned


def _key(path: Path | str) -> str:
    return os.path.normcase(os.path.abspath(path))


def _folder_name(root: Path) -> str:
    return root.name or root.drive.replace(":", "").strip("\\/") or "Folder"


def scan_paths(
    paths: Iterable[str | Path],
    *,
    known: Iterable[Path] = (),
    progress: Callable[[int], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> ScanResult:
    """Collect supported images from ``paths`` (files and/or folders, any depth).

    Folders are walked recursively; the relative path of every image starts with
    the folder's name so the output can mirror the structure. Unsupported files
    are counted in ``skipped``. Paths in ``known`` (already queued) and repeated
    paths are counted as duplicates.
    """
    result = ScanResult()
    seen = {_key(p) for p in known}

    def add(path: Path, relative: PurePath) -> None:
        fmt = format_from_path(path)
        if fmt is None:
            result.skipped += 1
            return
        key = _key(path)
        if key in seen:
            result.duplicates += 1
            return
        try:
            size = path.stat().st_size
        except OSError:
            result.skipped += 1
            return
        seen.add(key)
        result.items.append(SourceItem(path=path, relative=relative, format=fmt, size=size))
        if progress is not None and len(result.items) % 50 == 0:
            progress(len(result.items))

    for raw in paths:
        if cancelled is not None and cancelled():
            break
        path = Path(raw)
        if path.is_dir():
            top = PurePath(_folder_name(path))
            for dirpath, dirnames, filenames in os.walk(path):
                if cancelled is not None and cancelled():
                    break
                dirnames.sort(key=str.lower)
                base = Path(dirpath)
                rel_dir = top / base.relative_to(path)
                for name in sorted(filenames, key=str.lower):
                    add(base / name, rel_dir / name)
        elif path.is_file():
            add(path, PurePath(path.name))
        else:
            result.skipped += 1
    if progress is not None:
        progress(len(result.items))
    return result
