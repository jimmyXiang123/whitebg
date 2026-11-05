"""白底图转换工具 —— 批量把产品实拍图转成白底电商主图。

顶层包只放元信息，不导入任何重依赖（onnxruntime / rembg 都在真正用到时才导入），
因此 ``import whitebg`` 是毫秒级的，测试和打包分析都不会被拖慢。

常用入口::

    python -m whitebg                 # 打开图形界面
    python -m whitebg -i in -o out    # 命令行批处理
"""

__version__ = "2.1.0"
__author__ = "whitebg contributors"
__license__ = "MIT"

__all__ = ["__version__", "__author__", "__license__"]
