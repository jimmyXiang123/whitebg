# -*- coding: utf-8 -*-
"""Win7 兼容性静态体检：扫描打包目录里所有 PE 文件（.exe/.dll/.pyd），
找出只在 Windows 8 及以上才存在的依赖，以及 PE 子系统版本高于 6.1 的文件。

判定依据（保守，只报“确定 Win7 没有”的东西）：
  1. 导入 api-ms-win-core-path-l1-1-0.dll      —— Win8 引入的 API Set
  2. 导入 api-ms-win-core-synch-l1-2-0.dll     —— Win8（WaitOnAddress）
  3. 导入 api-ms-win-core-file-l1-2-2 等 >=l1-2 —— Win8 引入
  4. 导入 kernel32/kernelbase 里 Win8+ 才有的函数
  5. PE OptionalHeader.SubsystemVersion > 6.1
"""
from __future__ import annotations

import sys
from pathlib import Path

import pefile

WIN8_FUNCS = {
    "getsystemtimepreciseasfiletime",
    "waitonaddress",
    "wakebyaddresssingle",
    "wakebyaddressall",
    "setthreaddescription",
    "getthreaddescription",
    "prefetchvirtualmemory",
    "createfile2",
    "getoverlappedresultex",
    "copyfile2",
    "gettemppath2w",
    "compareobjecthandles",
    "getsystemcpusetinformation",
    "setthreadinformation",
    "openpackageinfo",
    "getpackagefullname",
    "processprng",
}

# Win8 之后才出现的 API Set 版本号后缀
BAD_APISET_HINTS = (
    "api-ms-win-core-path-l1-1-0",
    "api-ms-win-core-synch-l1-2-",
    "api-ms-win-core-file-l1-2-",
    "api-ms-win-core-file-l2-",
    "api-ms-win-core-winrt-",
    "api-ms-win-core-com-l1-1-2",
    "api-ms-win-core-handle-l1-1-0",
    "api-ms-win-core-threadpool-l1-2-",
    "api-ms-win-core-sysinfo-l1-2-",
    "api-ms-win-core-processthreads-l1-1-3",
)


def classify(path: Path):
    problems = []
    try:
        pe = pefile.PE(str(path), fast_load=True)
        pe.parse_data_directories(
            directories=[
                pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"],
                pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT"],
            ]
        )
    except Exception as exc:  # noqa: BLE001
        return [f"解析失败: {exc}"]

    ss_major, ss_minor = pe.OPTIONAL_HEADER.MajorSubsystemVersion, pe.OPTIONAL_HEADER.MinorSubsystemVersion
    if (ss_major, ss_minor) > (6, 1):
        problems.append(f"SubsystemVersion={ss_major}.{ss_minor} > 6.1")

    for attr in ("DIRECTORY_ENTRY_IMPORT", "DIRECTORY_ENTRY_DELAY_IMPORT"):
        for entry in getattr(pe, attr, []) or []:
            dll = entry.dll.decode(errors="ignore").lower()
            for hint in BAD_APISET_HINTS:
                if hint in dll:
                    problems.append(f"依赖 Win8+ API Set: {dll}")
                    break
            if dll in ("kernel32.dll", "kernelbase.dll", "api-ms-win-core-synch-l1-1-0.dll"):
                for imp in entry.imports:
                    if imp.name and imp.name.decode(errors="ignore").lower() in WIN8_FUNCS:
                        problems.append(f"依赖 Win8+ 函数: {dll}!{imp.name.decode(errors='ignore')}")
    pe.close()
    return problems


def main(root: str) -> int:
    root_p = Path(root)
    targets = [p for p in root_p.rglob("*") if p.suffix.lower() in (".exe", ".dll", ".pyd")]
    print(f"扫描 {len(targets)} 个 PE 文件：{root_p}")
    bad = 0
    for p in sorted(targets):
        probs = classify(p)
        if probs:
            bad += 1
            print(f"\n[!] {p.relative_to(root_p)}")
            for x in sorted(set(probs)):
                print(f"    - {x}")
    print(f"\n结果：{len(targets)} 个文件中 {bad} 个存在 Win8+ 依赖")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "dist_win7"))
