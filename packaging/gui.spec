# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置 —— Windows 10 / 11 版（现代依赖栈）。

用法（在仓库根目录执行）::

    pyinstaller --noconfirm --clean --distpath dist --workpath build packaging/gui.spec

产物：``dist/白底图转换GUI/``（文件夹版，双击里面的 exe 即用）。
"""

import importlib.metadata
import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, copy_metadata

# SPECPATH 由 PyInstaller 注入，指向本文件所在目录（packaging/）
ROOT = Path(SPECPATH).resolve().parent

# 1) 元数据：rembg / pymatting 等在 import 时用 importlib.metadata 查自己的版本，
#    冻结环境下找不到 dist-info 会抛 PackageNotFoundError，所以整体打包。
#    （只有几 KB，换来的是不依赖具体包的内部实现，更稳。）
_metadata_datas = []
for _dist in importlib.metadata.distributions():
    _name = _dist.metadata.get("Name")
    if _name:
        _metadata_datas += copy_metadata(_name)

# 2) tkinterdnd2 自带 Tcl/Tk 拖拽扩展（含二进制），必须整体收集
_tkdnd_datas, _tkdnd_binaries, _tkdnd_hidden = collect_all("tkinterdnd2")


def _fix_vc_binaries(binaries):
    """把打包进来的旧版 MSVC 运行库换成构建机 System32 里的新版。

    onnxruntime 由较新的 MSVC 编译，遇到旧版 MSVCP140 会初始化崩溃。
    """
    system32 = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"
    vc_names = {
        "msvcp140.dll", "msvcp140_1.dll", "msvcp140_2.dll",
        "msvcp140_atomic_wait.dll", "msvcp140_codecvt_ids.dll",
        "vcruntime140.dll", "vcruntime140_1.dll", "vcruntime140_threads.dll",
    }
    fixed = []
    for name, src, typ in binaries:
        if isinstance(name, str) and name.lower() in vc_names:
            sysv = system32 / name
            if sysv.exists():
                fixed.append((name, str(sysv), "BINARY"))
                continue
        fixed.append((name, src, typ))
    return fixed


a = Analysis(
    [str(ROOT / "run_gui.py")],
    pathex=[str(ROOT)],
    binaries=_tkdnd_binaries,
    datas=_metadata_datas + _tkdnd_datas,
    hiddenimports=["rembg.sessions", "tkinterdnd2"] + _tkdnd_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

a.binaries = _fix_vc_binaries(a.binaries)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="白底图转换GUI",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="白底图转换GUI",
)
