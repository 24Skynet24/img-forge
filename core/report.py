"""Text log of a processing run (for "Export log")."""
from __future__ import annotations

from datetime import datetime

from core.formats import format_info
from core.models import STATUS_LABELS, FileResult, summarize
from core.options import Mode, ProcessingOptions, QualityLevel
from core.utils import format_size

_MODE_LABELS = {
    Mode.COMPRESS: "Только сжатие",
    Mode.CONVERT: "Только конвертация",
    Mode.CONVERT_COMPRESS: "Конвертация + сжатие",
}
_QUALITY_LABELS = {
    QualityLevel.MAXIMUM: "Максимальное качество",
    QualityLevel.BALANCED: "Баланс",
    QualityLevel.SMALLEST: "Минимальный размер",
}


def format_log(results: list[FileResult], options: ProcessingOptions, elapsed: float = 0.0) -> str:
    """Render a human-readable log of ``results``."""
    summary = summarize(results)
    lines = [
        "ImgForge — журнал обработки",
        f"Дата: {datetime.now():%Y-%m-%d %H:%M:%S}",
        f"Режим: {_MODE_LABELS[options.mode]}",
    ]
    if options.mode is not Mode.COMPRESS:
        lines.append(f"Формат результата: {format_info(options.target_format).label}")
    if options.mode is not Mode.CONVERT:
        lines.append(f"Уровень сжатия: {_QUALITY_LABELS[options.quality]}")
    lines += [
        f"Удалять метаданные: {'да' if options.remove_metadata else 'нет'}",
        f"Потоков: {options.workers}",
        f"Время: {elapsed:.1f} с",
        "",
        f"Файлов: {summary.total} (OK: {summary.ok}, уже оптимизировано: "
        f"{summary.already_optimized}, ошибок: {summary.errors})",
        f"Размер: {format_size(summary.size_before)} → {format_size(summary.size_after)} "
        f"(сэкономлено {format_size(summary.saved_bytes)}, {summary.saved_percent:.1f}%)",
        "",
    ]
    for r in results:
        label = STATUS_LABELS[r.status]
        if r.ok:
            line = (
                f"[{label}] {r.source.path} — {format_size(r.original_size)} → "
                f"{format_size(r.new_size)} ({r.saved_percent:.1f}%)"
            )
        else:
            line = f"[{label}] {r.source.path} — {r.message}"
        if r.ok and r.warnings:
            line += f" | {'; '.join(r.warnings)}"
        lines.append(line)
    return "\n".join(lines) + "\n"
