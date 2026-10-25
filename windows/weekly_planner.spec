# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置。

生成 onedir 版本（启动更快，PySide6 体积大，不建议 onefile）：

    pip install pyinstaller
    pyinstaller weekly_planner.spec --noconfirm

产物：dist/WeeklyPlanner/WeeklyPlanner.exe
可以把整个 WeeklyPlanner 文件夹拷走使用，数据库仍然保存在
%APPDATA%\\WeeklyPlanner，升级程序不会丢数据。
"""

from pathlib import Path

ROOT = Path(SPECPATH)

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[],
    hiddenimports=[
        "PySide6.QtNetwork",
        "PySide6.QtWidgets",
        "PySide6.QtGui",
        "PySide6.QtCore",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "unittest",
        "pytest",
        "PySide6.Qt3DCore",
        "PySide6.QtQuick",
        "PySide6.QtQml",
        "PySide6.QtWebEngineCore",
        "PySide6.QtMultimedia",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="WeeklyPlanner",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "assets" / "app.ico"),
    version=str(ROOT / "version_info.txt"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="WeeklyPlanner",
)
