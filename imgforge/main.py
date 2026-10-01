"""ImgForge entry point.

Qt is imported lazily inside :func:`main`: with the Windows "spawn" start method
every worker process re-imports this module, and workers must stay Qt-free.
"""
from __future__ import annotations

import multiprocessing
import sys
from pathlib import Path


def _resource(relative: str) -> Path:
    """Locate a bundled data file (works from source and inside the PyInstaller exe)."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / relative


def _selftest(report: Path) -> int:
    """Process generated images into every output format using the real worker pool.

    ``ImgForge.exe --selftest result.txt`` verifies a frozen build (codecs bundled,
    worker processes start) without opening a window. Returns 0 when all passed.
    """
    import tempfile

    from PIL import Image

    from imgforge.core.formats import OUTPUT_FORMATS
    from imgforge.core.models import Status
    from imgforge.core.options import Mode, ProcessingOptions
    from imgforge.core.pipeline import BatchRunner
    from imgforge.core.scanner import scan_paths

    lines: list[str] = []
    failures = 0
    with tempfile.TemporaryDirectory(prefix="imgforge_selftest_") as tmp:
        src = Path(tmp) / "Photos" / "nested"
        src.mkdir(parents=True)
        photo = Image.effect_noise((320, 240), 60).convert("RGB")
        photo.save(src / "photo.jpg", quality=95)
        photo.convert("RGBA").save(src / "image.png")
        (src / "broken.jpg").write_bytes(b"not an image")
        items = scan_paths([Path(tmp) / "Photos"]).items
        for fmt in OUTPUT_FORMATS:
            options = ProcessingOptions(mode=Mode.CONVERT_COMPRESS, target_format=fmt, workers=2)
            outcome = BatchRunner(items, options, Path(tmp) / f"work_{fmt.value}").run()
            statuses = {r.source.name: r.status for r in outcome.results}
            good = (
                statuses.get("photo.jpg") is Status.OK
                and statuses.get("image.png") is Status.OK
                and statuses.get("broken.jpg") is Status.ERROR
            )
            failures += 0 if good else 1
            lines.append(f"{fmt.value}: {'OK' if good else 'FAIL'} {[(k, v.value) for k, v in statuses.items()]}")
    lines.append("SELFTEST " + ("PASSED" if failures == 0 else "FAILED"))
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0 if failures == 0 else 1


def main() -> int:
    """Start the GUI and return the exit code."""
    if len(sys.argv) >= 3 and sys.argv[1] == "--selftest":
        return _selftest(Path(sys.argv[2]))

    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    from imgforge.gui.main_window import MainWindow
    from imgforge.gui.settings import AppSettings
    from imgforge.gui.themes.manager import ThemeManager

    app = QApplication(sys.argv)
    app.setApplicationName("ImgForge")
    app.setOrganizationName("ImgForge")
    app.setStyle("Fusion")
    icon_path = _resource("assets/icon.ico")
    icon = QIcon(str(icon_path)) if icon_path.exists() else None
    if icon is not None:
        app.setWindowIcon(icon)

    settings = AppSettings.load()
    theme = ThemeManager(app, settings.theme)
    theme.apply()
    window = MainWindow(theme, settings, icon)
    window.show()
    return app.exec()


if __name__ == "__main__":
    multiprocessing.freeze_support()  # required for the frozen Windows exe
    raise SystemExit(main())
