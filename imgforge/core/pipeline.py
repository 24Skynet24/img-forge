"""Processing of single files and of whole batches in a pool of worker processes."""
from __future__ import annotations

import shutil
import sys
import threading
import time
from collections.abc import Callable, Sequence
from concurrent.futures import FIRST_COMPLETED, Future, ProcessPoolExecutor, wait
from concurrent.futures.process import BrokenProcessPool
from dataclasses import dataclass
from pathlib import Path, PurePath

from PIL import Image, UnidentifiedImageError

from imgforge.core import compressor
from imgforge.core.converter import Prepared, encode, prepare_image
from imgforge.core.formats import ImageFormat, format_info
from imgforge.core.models import FileResult, SourceItem, Status
from imgforge.core.options import Mode, ProcessingOptions


@dataclass(frozen=True)
class Task:
    """One unit of work for a worker process."""

    index: int
    item: SourceItem
    options: ProcessingOptions
    work_dir: Path


def describe_error(exc: BaseException) -> str:
    """Readable (Russian) reason for an exception raised while processing a file."""
    if isinstance(exc, UnidentifiedImageError):
        return "Файл повреждён или не является изображением"
    if isinstance(exc, Image.DecompressionBombError):
        return "Изображение слишком большое"
    if isinstance(exc, MemoryError):
        return "Недостаточно памяти для обработки изображения"
    if isinstance(exc, PermissionError):
        return "Нет доступа к файлу"
    if isinstance(exc, FileNotFoundError):
        return "Файл не найден"
    text = str(exc).strip()
    if isinstance(exc, OSError) and ("truncated" in text or "broken" in text.lower()):
        return "Файл повреждён или обрезан"
    return f"{type(exc).__name__}: {text}" if text else type(exc).__name__


def _output_relative(item: SourceItem, source_fmt: ImageFormat, out_fmt: ImageFormat) -> PurePath:
    """Relative output path: unchanged when the format is kept, new extension otherwise."""
    if out_fmt is source_fmt:
        return item.relative
    return item.relative.with_suffix(format_info(out_fmt).extension)


def _lossless_alternative(
    item: SourceItem, out_fmt: ImageFormat, options: ProcessingOptions, prepared: Prepared
) -> bytes | None:
    """Lossless re-optimisation of the original bytes (JPEG via mozjpeg, PNG via oxipng).

    Not used when it would change the picture: animated files and files whose
    EXIF orientation would be lost together with the metadata.
    """
    if out_fmt is not item.format or prepared.animated or prepared.orientation != 1:
        return None
    if out_fmt not in (ImageFormat.JPEG, ImageFormat.PNG):
        return None
    raw = item.path.read_bytes()
    if out_fmt is ImageFormat.JPEG:
        if not options.remove_metadata:
            copy = compressor.COPY_MARKERS.ALL
        elif prepared.had_icc:  # colours must not change; a profile is not private data
            copy = compressor.COPY_MARKERS.ICC
        else:
            copy = compressor.COPY_MARKERS.NONE
        return compressor.optimize_jpeg(raw, copy)
    level = compressor.PROFILES[options.quality].oxipng_level
    return compressor.oxipng_optimize(raw, level, keep_metadata=not options.remove_metadata)


def process_file(task: Task) -> FileResult:
    """Process one file. Never raises: failures are returned as ``Status.ERROR``."""
    started = time.perf_counter()
    item = task.item
    try:
        return _process(task, started)
    except Exception as exc:  # noqa: BLE001 - a broken file must never crash the batch
        return FileResult(
            index=task.index,
            status=Status.ERROR,
            source=item,
            original_size=item.size,
            message=describe_error(exc),
            elapsed=time.perf_counter() - started,
        )


def _process(task: Task, started: float) -> FileResult:
    item, options = task.item, task.options
    original_size = item.path.stat().st_size
    out_fmt = options.output_format_for(item.format)
    prepared = prepare_image(item.path, out_fmt, options)
    data = encode(
        prepared,
        out_fmt,
        compress=options.compress,
        level=options.quality,
        threads=options.threads_per_worker,
    )

    warnings = list(prepared.warnings)
    if options.mode is Mode.COMPRESS and out_fmt is not item.format:
        warnings.append(f"{item.format.value} сохранён как {format_info(out_fmt).label}")

    status = Status.OK
    relative = _output_relative(item, item.format, out_fmt)
    out_path = task.work_dir / f"{task.index:07d}{relative.suffix.lower()}"

    # Re-encoding the same format must never make the file bigger.
    if options.mode is not Mode.CONVERT and out_fmt is item.format and len(data) >= original_size:
        candidates = [data]
        alternative = _lossless_alternative(item, out_fmt, options, prepared)
        if alternative is not None:
            candidates.append(alternative)
        data = min(candidates, key=len)
        private_data_would_stay = options.remove_metadata and prepared.private_metadata
        if len(data) >= original_size and not private_data_would_stay:
            shutil.copy2(item.path, out_path)
            return FileResult(
                index=task.index,
                status=Status.ALREADY_OPTIMIZED,
                source=item,
                output_path=out_path,
                relative_output=relative,
                original_size=original_size,
                new_size=original_size,
                source_dims=prepared.source_size,
                output_dims=prepared.source_size,
                output_format=out_fmt,
                message="Уже оптимизировано — оригинал сохранён без изменений",
                warnings=tuple(warnings),
                elapsed=time.perf_counter() - started,
            )

    out_path.write_bytes(data)
    return FileResult(
        index=task.index,
        status=status,
        source=item,
        output_path=out_path,
        relative_output=relative,
        original_size=original_size,
        new_size=len(data),
        source_dims=prepared.source_size,
        output_dims=prepared.frames[0].size,
        output_format=out_fmt,
        message="; ".join(warnings),
        warnings=tuple(warnings),
        elapsed=time.perf_counter() - started,
    )


# --------------------------------------------------------------------------- batches


def _init_worker() -> None:
    """Worker start-up: import the codecs and lower the priority so the UI stays smooth."""
    if sys.platform == "win32":
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32
            kernel32.SetPriorityClass(kernel32.GetCurrentProcess(), 0x00004000)  # BELOW_NORMAL
        except Exception:  # pragma: no cover
            pass


@dataclass
class BatchOutcome:
    """Result of :meth:`BatchRunner.run`."""

    results: list[FileResult]
    cancelled: bool
    elapsed: float


class BatchRunner:
    """Runs :func:`process_file` for many items in a pool of worker processes.

    ``on_result`` is called (from the thread that calls :meth:`run`) after every
    finished item. Setting ``cancel`` stops submitting new work; running items
    finish normally and their results are kept.
    """

    def __init__(
        self,
        items: Sequence[SourceItem],
        options: ProcessingOptions,
        work_dir: Path,
        on_result: Callable[[FileResult], None] | None = None,
        cancel: threading.Event | None = None,
    ) -> None:
        self._items = list(items)
        self._options = options
        self._work_dir = work_dir
        self._on_result = on_result or (lambda _result: None)
        self._cancel = cancel or threading.Event()

    def _task(self, index: int) -> Task:
        return Task(index, self._items[index], self._options, self._work_dir)

    def _crash_result(self, index: int) -> FileResult:
        item = self._items[index]
        return FileResult(
            index=index,
            status=Status.ERROR,
            source=item,
            original_size=item.size,
            message="Обработка файла аварийно завершилась (файл повреждён?)",
        )

    def _isolate(self, indices: list[int], results: dict[int, FileResult]) -> None:
        """After a worker crash re-run the affected items one by one to find the culprit."""
        for index in indices:
            if self._cancel.is_set():
                break
            with ProcessPoolExecutor(1, initializer=_init_worker) as pool:
                try:
                    result = pool.submit(process_file, self._task(index)).result()
                except BrokenProcessPool:
                    result = self._crash_result(index)
            results[index] = result
            self._on_result(result)

    def run(self) -> BatchOutcome:
        """Process all items; blocks until done or cancelled."""
        started = time.perf_counter()
        self._work_dir.mkdir(parents=True, exist_ok=True)
        results: dict[int, FileResult] = {}
        pending = iter(range(len(self._items)))
        workers = max(1, min(self._options.workers, len(self._items)))
        in_flight: dict[Future[FileResult], int] = {}
        pool = ProcessPoolExecutor(workers, initializer=_init_worker) if self._items else None
        try:
            while pool is not None:
                broken: list[int] = []
                while not self._cancel.is_set() and len(in_flight) < workers * 2:
                    index = next(pending, None)
                    if index is None:
                        break
                    try:
                        in_flight[pool.submit(process_file, self._task(index))] = index
                    except BrokenProcessPool:
                        broken.append(index)
                        break
                if self._cancel.is_set():  # drop work that has not started yet
                    for future in list(in_flight):
                        if future.cancel():
                            del in_flight[future]
                if not in_flight and not broken:
                    break
                done, _ = wait(in_flight, timeout=0.2, return_when=FIRST_COMPLETED)
                for future in done:
                    index = in_flight.pop(future)
                    try:
                        result = future.result()
                    except BrokenProcessPool:
                        broken.append(index)
                        continue
                    except Exception as exc:  # noqa: BLE001
                        result = FileResult(
                            index=index, status=Status.ERROR, source=self._items[index],
                            original_size=self._items[index].size, message=describe_error(exc),
                        )
                    results[index] = result
                    self._on_result(result)
                if broken:
                    broken.extend(in_flight.values())
                    in_flight.clear()
                    pool.shutdown(wait=False, cancel_futures=True)
                    self._isolate(sorted(set(broken)), results)
                    pool = ProcessPoolExecutor(workers, initializer=_init_worker)
        finally:
            if pool is not None:
                pool.shutdown(wait=True, cancel_futures=True)
        ordered = [results[i] for i in sorted(results)]
        return BatchOutcome(ordered, self._cancel.is_set(), time.perf_counter() - started)
