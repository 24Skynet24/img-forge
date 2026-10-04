"""Pure text helpers for the main window (no widgets, no state)."""
from __future__ import annotations

from core.formats import INPUT_EXTENSIONS
from core.models import Summary
from core.options import Mode, ProcessingOptions, QualityLevel
from core.saver import SaveReport
from core.utils import format_size

FILES = ("файл", "файла", "файлов")
_QUALITY_TAGS = {QualityLevel.MAXIMUM: "MAX", QualityLevel.BALANCED: "BAL", QualityLevel.SMALLEST: "MIN"}


def file_filter() -> str:
    patterns = " ".join(f"*{ext}" for ext in sorted(INPUT_EXTENSIONS))
    return f"Изображения ({patterns});;Все файлы (*.*)"


def saved_text(summary: Summary) -> str:
    pct = summary.saved_percent
    return f"−{pct:.1f}%" if pct >= 0 else f"+{abs(pct):.1f}%"


def target_tag(options: ProcessingOptions) -> str:
    return "ИСХ." if options.mode is Mode.COMPRESS else options.target_format.value


def quality_tag(options: ProcessingOptions) -> str:
    return "—" if options.mode is Mode.CONVERT else _QUALITY_TAGS[options.quality]


def batch_summary_text(summary: Summary, total: int, cancelled: bool) -> str:
    head = (
        f"Отменено: обработано {summary.total} из {total}"
        if cancelled
        else f"Готово: {summary.ok + summary.already_optimized} из {summary.total}"
    )
    tail = f" · ошибок: {summary.errors}" if summary.errors else ""
    return f"{head}{tail} · сэкономлено {format_size(summary.saved_bytes)} ({summary.saved_percent:.1f}%)"


def save_report_text(report: SaveReport, dest: object) -> str:
    extra = []
    if report.renamed:
        extra.append(f"переименовано: {report.renamed}")
    if report.skipped:
        extra.append(f"пропущено: {report.skipped}")
    if report.errors:
        extra.append(f"ошибок: {len(report.errors)}")
    text = f"Сохранено файлов: {report.saved} → {dest}"
    return f"{text} ({', '.join(extra)})" if extra else text
