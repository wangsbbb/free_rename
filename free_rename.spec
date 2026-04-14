# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

project_dir = Path(__file__).resolve().parent

a = Analysis(
    [str(project_dir / 'free_rename.py')],
    pathex=[str(project_dir)],
    binaries=[],
    datas=[
        (str(project_dir / 'assets'), 'assets'),
        (str(project_dir / 'styles'), 'styles'),
    ],
    hiddenimports=[],
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
    name='free_rename',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=str(project_dir / 'version_info.txt'),
    icon=[str(project_dir / 'assets' / 'icons' / 'app_icon_final.ico')],
)
