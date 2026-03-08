# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


PROJECT_ROOT = Path(SPECPATH).resolve().parent

datas = [
    (str(PROJECT_ROOT / "README.md"), "."),
    (str(PROJECT_ROOT / "architecture.md"), "."),
    (str(PROJECT_ROOT / "config"), "config"),
    (str(PROJECT_ROOT / "assets"), "assets"),
    (str(PROJECT_ROOT / "macros"), "macros"),
    (str(PROJECT_ROOT / "schemas"), "schemas"),
]
datas += collect_data_files("easyocr")
datas += collect_data_files("playwright")

hiddenimports = []
hiddenimports += collect_submodules("playwright")
hiddenimports += collect_submodules("pywinauto")
hiddenimports += collect_submodules("winsdk")


a = Analysis(
    [str(PROJECT_ROOT / "src" / "aiautomouse" / "cli.py")],
    pathex=[str(PROJECT_ROOT / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[str(PROJECT_ROOT / "packaging" / "hooks")],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["jax", "jaxlib", "jax_cuda12_plugin"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="aiautomouse",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)

gui_exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="aiautomouse-gui",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)

coll = COLLECT(
    exe,
    gui_exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="aiautomouse",
)
