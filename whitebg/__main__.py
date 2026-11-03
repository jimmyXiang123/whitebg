"""``python -m whitebg`` 的统一入口：不带参数开界面，带参数走命令行批处理。

例子::

    python -m whitebg                          # 图形界面
    python -m whitebg -i input -o output       # 命令行批处理
    python -m whitebg --gui                    # 显式打开界面
"""

from __future__ import annotations

import sys


def main() -> None:
    args = sys.argv[1:]
    if args and args != ["--gui"]:
        from .engine import launch as cli_launch

        cli_launch()
        return

    from .gui import launch as gui_launch

    gui_launch()


if __name__ == "__main__":
    main()
