# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec: one portable, windowed ImgForge.exe with every codec bundled.
#
#     pyinstaller build.spec --noconfirm
#
# The result is dist/ImgForge.exe.
from PyInstaller.utils.hooks import collect_all

datas = [("assets/icon.ico", "assets")]
binaries = []
hiddenimports = []

# Packages with native extensions / data files that static analysis can miss.
for package in ("pillow_heif", "imagequant", "oxipng", "mozjpeg_lossless_optimization"):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(package)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

a = Analysis(
    ["imgforge/main.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "numpy",
        "PySide6.QtNetwork",
        "PySide6.QtQml",
        "PySide6.QtQuick",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtMultimedia",
        "PySide6.Qt3DCore",
        "PySide6.QtCharts",
        "PySide6.QtSql",
        "PySide6.QtTest",
        "PySide6.QtPdf",
        "PySide6.QtSvg",
        "pytest",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="ImgForge",
    icon="assets/icon.ico",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,  # windowed application
    disable_windowed_traceback=False,
)
