"""Scanner, batch runner (process pool), corrupted files, structure mirroring and saving."""
from __future__ import annotations

import threading
from pathlib import Path, PurePath

import pytest
from PIL import Image

from core.formats import ImageFormat
from core.models import FileResult, Status, summarize
from core.options import Mode, ProcessingOptions
from core.pipeline import BatchRunner, Task, process_file
from core.report import format_log
from core.saver import ConflictAction, SaveEntry, save_outputs
from core.scanner import scan_paths

from .conftest import gradient_image, make_item, save_as


@pytest.fixture
def photos(tmp_path: Path) -> Path:
    """Photos/{a.jpg, notes.txt, sub/b.png, sub/deep/c.WEBP, sub/deep/readme.md}"""
    root = tmp_path / "src" / "Photos"
    (root / "sub" / "deep").mkdir(parents=True)
    save_as(gradient_image((50, 40)), root / "a.jpg", ImageFormat.JPEG)
    save_as(gradient_image((40, 50)), root / "sub" / "b.png", ImageFormat.PNG)
    save_as(gradient_image((30, 30)), root / "sub" / "deep" / "c.WEBP", ImageFormat.WEBP)
    (root / "notes.txt").write_text("hello")
    (root / "sub" / "deep" / "readme.md").write_text("# hi")
    return root


# ------------------------------------------------------------------ scanner


def test_scanner_walks_nested_folders_and_counts_skipped(photos: Path, tmp_path: Path) -> None:
    loose = save_as(gradient_image((20, 20)), tmp_path / "loose.bmp", ImageFormat.BMP)
    result = scan_paths([photos, loose])
    rels = {str(i.relative) for i in result.items}
    assert rels == {
        str(PurePath("Photos/a.jpg")),
        str(PurePath("Photos/sub/b.png")),
        str(PurePath("Photos/sub/deep/c.WEBP")),
        "loose.bmp",
    }
    assert result.skipped == 2  # notes.txt, readme.md
    assert {i.format for i in result.items} == {ImageFormat.JPEG, ImageFormat.PNG, ImageFormat.WEBP, ImageFormat.BMP}


def test_scanner_ignores_unsupported_loose_files_and_duplicates(photos: Path, tmp_path: Path) -> None:
    txt = tmp_path / "x.txt"
    txt.write_text("x")
    first = scan_paths([photos])
    again = scan_paths([photos, photos / "a.jpg", txt], known=[i.path for i in first.items])
    assert again.items == []
    assert again.skipped == 3  # x.txt plus notes.txt and readme.md inside the folder
    assert again.duplicates == 4


def test_scanner_handles_missing_paths(tmp_path: Path) -> None:
    result = scan_paths([tmp_path / "nope.png"])
    assert result.items == [] and result.skipped == 1


def test_scanner_cancel(photos: Path) -> None:
    result = scan_paths([photos], cancelled=lambda: True)
    assert result.items == []


# ------------------------------------------------------------------ corrupted input


@pytest.mark.parametrize("name", ["bad.jpg", "bad.png", "bad.webp", "bad.gif", "bad.tiff", "bad.heic", "bad.avif"])
def test_corrupted_file_is_reported_not_raised(tmp_path: Path, work_dir: Path, name: str) -> None:
    bad = tmp_path / name
    bad.write_bytes(b"this is definitely not an image" * 10)
    result = process_file(Task(0, make_item(bad), ProcessingOptions(workers=1), work_dir))
    assert result.status is Status.ERROR
    assert result.message and result.output_path is None


def test_truncated_file_is_an_error(tmp_path: Path, work_dir: Path) -> None:
    good = save_as(gradient_image((200, 200)), tmp_path / "cut.png", ImageFormat.PNG)
    data = good.read_bytes()
    good.write_bytes(data[: len(data) // 2])
    result = process_file(Task(0, make_item(good), ProcessingOptions(workers=1), work_dir))
    assert result.status is Status.ERROR


def test_missing_file_is_an_error(tmp_path: Path, work_dir: Path) -> None:
    path = save_as(gradient_image((10, 10)), tmp_path / "gone.png", ImageFormat.PNG)
    item = make_item(path)
    path.unlink()
    result = process_file(Task(0, item, ProcessingOptions(workers=1), work_dir))
    assert result.status is Status.ERROR


# ------------------------------------------------------------------ batch runner


def test_batch_continues_after_a_broken_file(photos: Path, tmp_path: Path, work_dir: Path) -> None:
    (photos / "broken.jpg").write_bytes(b"\xff\xd8\xff garbage")
    items = scan_paths([photos]).items
    seen: list[FileResult] = []
    outcome = BatchRunner(
        items, ProcessingOptions(mode=Mode.CONVERT_COMPRESS, target_format=ImageFormat.WEBP, workers=2),
        work_dir, on_result=seen.append,
    ).run()
    assert not outcome.cancelled
    assert len(outcome.results) == len(items) == len(seen) == 4
    assert [r.index for r in outcome.results] == [0, 1, 2, 3]
    errors = [r for r in outcome.results if r.status is Status.ERROR]
    assert [r.source.name for r in errors] == ["broken.jpg"]
    assert all(r.output_path and r.output_path.exists() for r in outcome.results if r.ok)
    summary = summarize(outcome.results)
    assert (summary.total, summary.errors) == (4, 1)


def test_batch_cancel_stops_early(tmp_path: Path, work_dir: Path) -> None:
    items = []
    for i in range(40):
        path = save_as(gradient_image((300, 300)), tmp_path / f"i{i:02d}.png", ImageFormat.PNG)
        items.append(make_item(path))
    cancel = threading.Event()
    seen: list[FileResult] = []

    def on_result(result: FileResult) -> None:
        seen.append(result)
        cancel.set()

    outcome = BatchRunner(
        items, ProcessingOptions(mode=Mode.COMPRESS, workers=2), work_dir, on_result=on_result, cancel=cancel
    ).run()
    assert outcome.cancelled
    assert 1 <= len(outcome.results) < len(items)


def test_empty_batch(work_dir: Path) -> None:
    outcome = BatchRunner([], ProcessingOptions(workers=2), work_dir).run()
    assert outcome.results == [] and not outcome.cancelled


def test_log_and_summary(photos: Path, work_dir: Path) -> None:
    (photos / "broken.png").write_bytes(b"nope")
    options = ProcessingOptions(mode=Mode.COMPRESS, workers=2)
    outcome = BatchRunner(scan_paths([photos]).items, options, work_dir).run()
    log = format_log(outcome.results, options, outcome.elapsed)
    assert "broken.png" in log and "Ошибка" in log and "Photos" in log
    summary = summarize(outcome.results)
    assert summary.size_before >= summary.size_after > 0


# ------------------------------------------------------------------ mirroring & saving


def process_all(items, work_dir: Path, **kwargs) -> list[FileResult]:
    options = ProcessingOptions(workers=1, **kwargs)
    return [process_file(Task(i, item, options, work_dir)) for i, item in enumerate(items)]


def entries_for(results: list[FileResult]) -> list[SaveEntry]:
    return [SaveEntry(r.output_path, r.relative_output) for r in results if r.ok]


def skip_all(_path: Path, _is_dir: bool) -> ConflictAction:
    raise AssertionError("no conflict expected")


def test_nested_structure_is_mirrored_with_new_extensions(photos: Path, tmp_path: Path, work_dir: Path) -> None:
    loose = save_as(gradient_image((20, 20)), tmp_path / "loose.png", ImageFormat.PNG)
    items = scan_paths([photos, loose]).items
    results = process_all(items, work_dir, mode=Mode.CONVERT, target_format=ImageFormat.WEBP)
    dest = tmp_path / "out"
    report = save_outputs(entries_for(results), dest, skip_all)
    assert report.saved == 4 and not report.errors
    found = {str(p.relative_to(dest)) for p in dest.rglob("*") if p.is_file()}
    assert found == {
        str(PurePath("Photos/a.webp")),
        str(PurePath("Photos/sub/b.webp")),
        str(PurePath("Photos/sub/deep/c.WEBP")),  # format unchanged -> name kept as is
        "loose.webp",
    }
    # No stray files (notes.txt, readme.md) and originals untouched.
    assert (photos / "a.jpg").exists() and (photos / "notes.txt").exists()
    with Image.open(dest / "Photos" / "sub" / "b.webp") as img:
        assert img.format == "WEBP" and img.size == (40, 50)


def test_compress_only_keeps_names(photos: Path, tmp_path: Path, work_dir: Path) -> None:
    items = scan_paths([photos]).items
    results = process_all(items, work_dir, mode=Mode.COMPRESS)
    dest = tmp_path / "out"
    save_outputs(entries_for(results), dest, skip_all)
    assert (dest / "Photos" / "a.jpg").exists()
    assert (dest / "Photos" / "sub" / "deep" / "c.WEBP").exists()


def _simple_entries(tmp_path: Path, names: list[str]) -> list[SaveEntry]:
    work = tmp_path / "w"
    work.mkdir(exist_ok=True)
    entries = []
    for i, name in enumerate(names):
        f = work / f"{i}.bin"
        f.write_text(f"new-{name}")
        entries.append(SaveEntry(f, PurePath(name)))
    return entries


@pytest.mark.parametrize(
    "action, expected_files",
    [
        (ConflictAction.OVERWRITE, {"a.txt": "new-a.txt"}),
        (ConflictAction.RENAME, {"a.txt": "old", "a_1.txt": "new-a.txt"}),
        (ConflictAction.SKIP, {"a.txt": "old"}),
    ],
)
def test_file_conflicts(tmp_path: Path, action, expected_files) -> None:
    dest = tmp_path / "dest"
    dest.mkdir()
    (dest / "a.txt").write_text("old")
    calls = []

    def resolver(path: Path, is_dir: bool) -> ConflictAction:
        calls.append((path.name, is_dir))
        return action

    report = save_outputs(_simple_entries(tmp_path, ["a.txt"]), dest, resolver)
    assert calls == [("a.txt", False)]
    assert {p.name: p.read_text() for p in dest.iterdir()} == expected_files
    assert report.skipped == (1 if action is ConflictAction.SKIP else 0)
    assert report.renamed == (1 if action is ConflictAction.RENAME else 0)


@pytest.mark.parametrize("action", list(ConflictAction))
def test_folder_conflicts_are_asked_once_per_folder(tmp_path: Path, action) -> None:
    dest = tmp_path / "dest"
    (dest / "Photos").mkdir(parents=True)
    (dest / "Photos" / "keep.txt").write_text("old")
    names = ["Photos/a.txt", "Photos/sub/b.txt", "Photos/sub/c.txt"]
    calls = []

    def resolver(path: Path, is_dir: bool) -> ConflictAction:
        calls.append((path.name, is_dir))
        return action

    save_outputs(_simple_entries(tmp_path, [n.replace("/", "\\") if False else n for n in names]), dest, resolver)
    assert calls == [("Photos", True)]
    assert (dest / "Photos" / "keep.txt").read_text() == "old"  # never deleted
    if action is ConflictAction.OVERWRITE:
        assert (dest / "Photos" / "sub" / "b.txt").exists()
    elif action is ConflictAction.RENAME:
        assert (dest / "Photos_1" / "sub" / "c.txt").exists()
        assert not (dest / "Photos" / "a.txt").exists()
    else:
        assert not (dest / "Photos" / "a.txt").exists() and not (dest / "Photos_1").exists()


def test_clashes_between_queued_items_are_renamed(tmp_path: Path) -> None:
    dest = tmp_path / "dest"
    entries = _simple_entries(tmp_path, ["same.webp", "same.webp", "same.webp"])
    report = save_outputs(entries, dest, skip_all)
    assert sorted(p.name for p in dest.iterdir()) == ["same.webp", "same_1.webp", "same_2.webp"]
    assert report.saved == 3 and report.renamed == 2


def test_save_can_be_cancelled(tmp_path: Path) -> None:
    dest = tmp_path / "dest"
    entries = _simple_entries(tmp_path, ["a.webp", "b.webp", "c.webp"])
    counter = {"n": 0}

    def cancelled() -> bool:
        counter["n"] += 1
        return counter["n"] > 1

    report = save_outputs(entries, dest, skip_all, cancelled=cancelled)
    assert report.cancelled and report.saved == 1


def test_pixel_limit_is_disabled() -> None:
    assert Image.MAX_IMAGE_PIXELS is None
