# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for the Pages Counter GUI.
#
# Produces a single self-contained executable (one-file, windowed).
# Build it on the target OS (build on Windows to get a .exe):
#
#     pyinstaller gui.spec
#
# Result: dist/PagesCounter.exe  (Windows)  /  dist/PagesCounter  (Linux/macOS)
#
# NOTE: PyInstaller does not cross-compile. Run this ON Windows to get a .exe.

from PyInstaller.utils.hooks import collect_data_files

# CustomTkinter ships its color themes (JSON) and bundled Roboto fonts as
# package data. PyInstaller does not collect these automatically, and without
# them the frozen GUI fails to start (it can't find its theme/font assets).
datas = collect_data_files("customtkinter")


a = Analysis(
    ['gui.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    # gui.py imports services directly, but list it explicitly so the build
    # never silently drops the domain layer.
    hiddenimports=['services'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='PagesCounter',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    # Windowed app: no console window pops up alongside the GUI on Windows.
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
