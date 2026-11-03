#!/usr/bin/env python
"""图形界面启动入口。

* 直接运行：``python run_gui.py``
* PyInstaller 打包也指向这个文件（见 ``packaging/*.spec``），
  这样包内可以用相对导入，不必把 ``whitebg/gui.py`` 当顶层脚本拆开。
"""

from whitebg.gui import launch

if __name__ == "__main__":
    launch()
