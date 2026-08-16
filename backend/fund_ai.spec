# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置（在 backend/ 目录运行: pyinstaller fund_ai.spec）

产物: backend/dist/FundAI/（one-folder 原生客户端）
      由 Inno Setup 进一步封装为安装器（见 installer/fund_ai.iss）。

客户端形态：窗口化（console=False），界面由 WebView2 渲染在原生窗口中，
无命令行窗口、无浏览器依赖。日志写入 %LOCALAPPDATA%/FundAI/logs。
"""
from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
)

BACKEND_DIR = Path(SPECPATH)  # noqa: F821  spec 运行时注入
FRONTEND_DIST = (BACKEND_DIR.parent / "frontend" / "dist").resolve()

hiddenimports = []
for pkg in ("uvicorn", "apscheduler", "aiosmtplib", "webview", "clr_loader"):
    try:
        hiddenimports += collect_submodules(pkg)
    except Exception:  # noqa: BLE001
        pass
hiddenimports += [
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
    "email_validator",
    "multipart",
    "clr",
    "webview.platforms.edgechromium",
    "webview.platforms.winforms",
]

datas = []
if FRONTEND_DIST.exists():
    datas.append((str(FRONTEND_DIST), "frontend_dist"))
custom_dir = BACKEND_DIR / "data" / "custom"
if custom_dir.exists():
    datas.append((str(custom_dir), "data/custom"))
for pkg in ("sklearn", "scipy", "pandas", "webview", "pythonnet", "clr_loader"):
    try:
        datas += collect_data_files(pkg)
    except Exception:  # noqa: BLE001
        pass

binaries = []
for pkg in ("pythonnet", "clr_loader"):
    try:
        binaries += collect_dynamic_libs(pkg)
    except Exception:  # noqa: BLE001
        pass

a = Analysis(
    ["desktop_entry.py"],
    pathex=[str(BACKEND_DIR)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "PyQt5", "PySide2", "matplotlib", "IPython", "notebook"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="FundAI",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # 原生客户端窗口：不显示命令行窗口
    icon=str(BACKEND_DIR.parent / "assets" / "fundai.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="FundAI",
)
