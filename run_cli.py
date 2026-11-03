#!/usr/bin/env python
"""命令行启动入口。

* 直接运行：``python run_cli.py -i input -o output``
* PyInstaller 打包命令行 exe 时指向这个文件（见 ``packaging/*.spec``）
"""

from whitebg.engine import launch

if __name__ == "__main__":
    launch()
