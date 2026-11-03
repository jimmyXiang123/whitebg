# 打包成 exe

源码运行只需要 `pip install -r requirements.txt`；如果你要发给不懂 Python 的同事，
可以打成"解压就能双击"的文件夹版。

## 一、准备

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-build.txt
```

## 二、打包（Windows 10 / 11）

```bash
pyinstaller --noconfirm --clean --distpath dist --workpath build packaging/gui.spec
```

产物：`dist/白底图转换GUI/`，把**整个文件夹**拷走，双击里面的 `白底图转换GUI.exe` 即可。
不要只拷 exe——依赖都在同目录里。

## 三、打包前必须做的一件事（numba 缓存）

`pymatting` 用 `numba` 的 `@njit(cache=True)` 做 JIT 加速。冻结成 exe 后 numba 找不到
源码文件，缓存机制会直接抛异常。所以打包前要把这些 `cache=True` 改成 `cache=False`：

```bash
python - <<'PY'
from pathlib import Path
n = 0
for p in Path(".venv/Lib/site-packages/pymatting").rglob("*.py"):
    s = p.read_text(encoding="utf-8")
    if "cache=True" in s:
        n += s.count("cache=True")
        p.write_text(s.replace("cache=True", "cache=False"), encoding="utf-8")
print("已改写", n, "处")
PY
```

只改虚拟环境里的副本，不影响系统里已安装的同名包。

## 四、模型权重怎么处理

两种策略，按交付方式选：

| 策略 | 做法 | 优点 | 缺点 |
|---|---|---|---|
| 随包带权重 | 把 `models/models/<名字>/` 整个放到 exe 同级目录 | 客户零等待、可离线 | 每个模型 40MB~1GB，包会很大 |
| 不带权重 | 什么都不做 | 包小 | 客户首次运行要联网下载 |

程序启动时会按 `exe 同级/models` → `上一级/models` 的顺序找权重，都没有才联网。
`init_runtime()` 里的 `REMBG_HOME` / `U2NET_HOME` 就是干这个的。

## 五、为什么要文件夹版而不是单文件

单文件（`--onefile`）每次启动都要把上百 MB 解压到 `%TEMP%`：老机器上启动要几十秒，
临时目录被清理或被杀软扫描时还可能直接失败。文件夹版启动快、故障面小，
整个目录拷走一样是"绿色版"。

## 六、常见交付问题

| 现象 | 原因 / 处理 |
|---|---|
| SmartScreen「已保护你的电脑」 | 未做代码签名，点「更多信息 → 仍要运行」 |
| 杀软报毒 / 直接删文件 | PyInstaller 程序的常见误报，加信任或提交误报 |
| 双击一闪而过 | 看同目录 `启动日志.txt`，GUI 版崩溃时会弹窗并写日志 |
| 换了台机器打不开 | 32 位系统装不了；或系统低于 Win10 —— 走 [windows7.md](windows7.md) |
| 想减小体积 | 在 spec 的 `excludes` 里加用不到的包；只保留实际要用的模型 |

## 七、命令行版

仓库只提供了 GUI 的 spec。想要无界面的 exe，复制 `packaging/gui.spec`，
把 `Analysis` 的入口改成 `run_cli.py`、`EXE` 里 `console=True` 即可。
