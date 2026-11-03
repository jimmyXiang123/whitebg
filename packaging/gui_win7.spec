# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置 —— Windows 7 兼容版。

为什么要单独一份配置：

* Python 3.9+ 的 ``python3xx.dll`` 静态依赖 ``api-ms-win-core-path-l1-1-0.dll``，
  而该 DLL 是 Windows 8 才引入的 API Set，Win7 上不存在 → 双击即报
  "无法启动此程序，因为计算机中丢失 api-ms-win-core-path-l1-1-0.dll"。
  所以必须在 **Python 3.8** 环境里打包（见 docs/windows7.md）。
* ONNX Runtime 自 1.15.0 起正式放弃 Win7，故依赖锁定 ``onnxruntime==1.14.1``。
* PyInstaller 5.13.2 的 bootloader 仍以 Win7 为目标平台（6.x 已放弃）。

用法（在仓库根目录、已激活 Python 3.8 环境时执行）::

    pyinstaller --noconfirm --clean --distpath dist_win7 --workpath build_win7 packaging/gui_win7.spec
"""

import importlib.metadata
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, copy_metadata

ROOT = Path(SPECPATH).resolve().parent

# 1) 元数据：rembg / pymatting 等会在 import 时查自己的版本，冻结后找不到 dist-info 会报错
_metadata_datas = []
for _dist in importlib.metadata.distributions():
    _name = _dist.metadata.get("Name")
    if _name:
        _metadata_datas += copy_metadata(_name)

# 2) tkinterdnd2 自带 Tcl/Tk 拖拽扩展（含二进制），必须整体收集
_tkdnd_datas, _tkdnd_binaries, _tkdnd_hidden = collect_all("tkinterdnd2")

# 3) rembg 的会话实现是运行时才 import 的，必须显式声明
_hidden = [
    "rembg.sessions",
    "rembg.sessions.u2net",
    "rembg.sessions.isnet",
    "rembg.sessions.birefnet",
    "rembg.sessions.base",
    "tkinterdnd2",
] + _tkdnd_hidden

a = Analysis(
    [str(ROOT / "run_gui.py")],
    pathex=[str(ROOT)],
    binaries=_tkdnd_binaries,
    datas=_metadata_datas + _tkdnd_datas,
    hiddenimports=_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 明显用不到的大件，剔掉可减小体积、也少踩 Win7 的坑
        "matplotlib", "pandas", "notebook", "IPython", "pytest",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)


# 4) 剔除构建机自带的 UCRT（ucrtbase.dll + api-ms-win-*）。
#    PyInstaller 会从 Windows 10/11 的 System32 里把这些依赖抓进来，而它们的
#    SubsystemVersion=10.0、且依赖 Win8+ 才有的 API Set，拷到 Win7 上加载必失败。
#    去掉后由目标机自己的 System32 提供（Win7 SP1 + KB2999226 即 UCRT 补丁），
#    这也是微软对 Win7 应用的推荐做法。
def _drop_win10_ucrt(binaries):
    kept, dropped = [], 0
    for name, src, typ in binaries:
        low = str(name).lower()
        if low.startswith("api-ms-win-") or low == "ucrtbase.dll":
            dropped += 1
            continue
        kept.append((name, src, typ))
    print(f"[win7] 已剔除构建机自带 UCRT 共 {dropped} 个文件（改用目标机系统 UCRT）")
    return kept


a.binaries = _drop_win10_ucrt(a.binaries)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="白底图转换GUI",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # UPX 压缩过的系统 DLL 在个别 Win7 机器上会被杀软误报/加载失败，这里关闭
    upx=False,
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
    upx=False,
    upx_exclude=[],
    name="白底图转换GUI",
)
