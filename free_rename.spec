# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['C:\\Users\\sexer\\Desktop\\豆瓣工具\\批量重命名\\free_rename_v1.0_github\\free_rename.py'],
    pathex=[],
    binaries=[],
    datas=[('assets', 'assets'), ('styles', 'styles')],
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
    version='C:\\Users\\sexer\\Desktop\\豆瓣工具\\批量重命名\\free_rename_v1.0_github\\version_info.txt',
    icon=['C:\\Users\\sexer\\Desktop\\豆瓣工具\\批量重命名\\free_rename_v1.0_github\\assets\\icons\\app_icon_final.ico'],
)
