# Windows 7 兼容构建

> 目标：让这个工具能在 **64 位 Windows 7 SP1** 上直接运行，而不是双击就报缺 DLL。
> 本文记录版本天花板、必须的系统组件、打包时的坑，以及在 Win10/11 上能做的静态验证。

---

## 一、结论

用 Python 3.9+ 打的包，在 Win7 上双击会报
`无法启动此程序，因为计算机中丢失 api-ms-win-core-path-l1-1-0.dll`。

根因：`python3xx.dll` 静态依赖 Windows 8 才引入的 API Set
`api-ms-win-core-path-l1-1-0.dll`，Win7 上不存在这个系统组件，加载器直接拒绝启动
（此时 Python 代码一行都还没跑）。

解决办法是改用 **Python 3.8.20 + PyInstaller 5.13.2** 构建，并把推理引擎降到
**ONNX Runtime 1.14.1**（微软从 1.15.0 起正式放弃 Win7）。实测：

- 162 个 PE 文件静态扫描，**0 个**依赖 Win8+ 的 API Set 或函数
- 打包后 exe 在无任何环境变量、无任何安装动作的情况下启动并成功出图
- 转换速度与旧版基本持平（u2net 持平，BiRefNet 慢约 29%）

---

## 二、依赖清单

### 运行时（已全部打进目录，用户无需安装）

| 组件 | 版本 | 作用 | 备注 |
|---|---|---|---|
| Python | 3.8.20 (64-bit) | 解释器 | 3.8 是最后一个官方支持 Win7 的版本 |
| PyInstaller | 5.13.2 | 打包器/bootloader | 6.x 的 bootloader 已放弃 Win7 |
| ONNX Runtime | **1.14.1** | 模型推理 | 1.15.0 起不再支持 Win7，这是天花板 |
| rembg | 2.0.61 | 抠图调度 | py3.8 能装的最高版 |
| numpy | 1.24.4 | 数值计算 | 最后一个支持 py3.8 的版本 |
| scipy | 1.10.1 | 形态学/滤波 | 与 numpy 1.24 配套 |
| Pillow | 9.5.0 | 图像读写 | |
| opencv-python-headless | 4.5.5.64 | rembg 依赖 | 4.5.x 是 Win7 上最稳的 OpenCV |
| PyMatting | 1.1.12 | 边缘去色/精细蒙版 | 打包前已把 `cache=True` 改成 `cache=False` |
| numba | 0.58.1 | PyMatting 的 JIT | |
| llvmlite | 0.41.1 | numba 的 LLVM 后端 | |
| pooch / requests / tqdm | — | 模型下载（离线用不到） | 保留是为了异常时能回退下载 |
| tkinterdnd2 | 0.3.0 | 拖拽支持 | |

### 构建期（只在重新打包时需要）

`pyinstaller==5.13.2`、`pyinstaller-hooks-contrib`、`pefile`（静态体检脚本用）。

准备一个独立的 Python 3.8 环境（不要污染主环境的 3.11+）：

```bash
py -3.8 -m venv .venv38
.venv38\Scripts\python -m pip install -r requirements-win7.txt
```

然后打包（在仓库根目录执行）：

```bash
.venv38\Scripts\python -m PyInstaller --noconfirm --clean ^
    --distpath dist_win7 --workpath build_win7 packaging/gui_win7.spec
```

---

## 三、运行环境要求

| 项目 | 要求 |
|---|---|
| 操作系统 | Windows 7 **SP1** / 8.1 / 10 / 11，**仅 64 位** |
| CPU | 支持 SSE2 的 x64（2008 年后的机器基本都满足） |
| 内存 | 最低 4GB，建议 8GB（大图 + 质量模型峰值约 2.5GB） |
| 磁盘 | 约 3GB（程序 349MB + 模型 1.5GB + 输出） |
| 系统补丁 | Win7 需 **KB2999226（UCRT）**；这是 Windows Update 常规补丁，绝大多数机器已有 |
| 额外安装 | **不需要**装 Python、**不需要**装 VC++ 运行库（`MSVCP140/VCRUNTIME140` 已内置） |
| 网络 | 不需要（模型随包） |

### 关于 UCRT 的处理（重要）

打包时 PyInstaller 会把**构建机 Win11 的 UCRT**（`ucrtbase.dll` + 40 个 `api-ms-win-*`）
一起收集进来，这些文件 `SubsystemVersion=10.0`、依赖 Win8+ 的 API Set，拷到 Win7 必炸。
因此 `packaging/gui_win7.spec` 里加了 `_drop_win10_ucrt()`，**主动剔除 41 个文件**，
改由目标机自己的 System32 提供。这正是微软对 Win7 应用的推荐做法。

代价：Win7 必须装有 UCRT 补丁。没有的话会提示
`丢失 api-ms-win-crt-runtime-l1-1-0.dll`，装一次 `vc_redist.x64.exe` 即可。

---

## 四、为兼容做的三处代码改动（`whitebg/engine.py`）

| 改动 | 原因 | 对现代版（Python 3.11+）的影响 |
|---|---|---|
| `init_runtime()` 同时设置 `U2NET_HOME` | 老版 rembg 只认这个变量，新版认 `REMBG_HOME` | 无（多设一个环境变量而已） |
| `_bind_local_models()` | 老版按 `models/<名>.onnx` 平铺查找，新版按 `models/<名>/<名>.onnx` 子目录查找；直接改写各会话类的 `download_models` 指向本地权重，避免联网下载 | 无（命中同一个文件） |
| `cutout_subject()` 增加版本分支 + `_decontaminate_cutout()` | 老版 rembg 没有 `decontaminate` 参数（边缘去色会被静默丢弃）。用 `only_mask` 取蒙版后，调用 pymatting 的 `estimate_foreground_ml` 复刻同样效果 | 无（新版走原路径，行为完全一致） |


---

## 五、验证结果

### 1) 静态兼容性体检（`packaging/scan_win7.py`）

```
扫描 162 个 PE 文件：dist_win7
结果：162 个文件中 0 个存在 Win8+ 依赖
```

检查项：导入的 API Set 是否 Win8+、`kernel32/kernelbase` 是否用了 Win8+ 函数、
PE `SubsystemVersion` 是否高于 6.1。

关键文件逐个确认干净：`python38.dll`、`onnxruntime*.dll`、`numpy`、`cv2`、`llvmlite`、`tkinter`。

### 2) 冒烟测试（真实启动打包产物）

`GUI_SMOKE=1` 模式（自动处理 `input/` 后退出），不设任何环境变量：

```
[GUI] 启动 白底图转换工具（拖拽支持：开）
[模型] u2net 就绪，耗时 0.5s
[完成] 成功 1 张，失败 0 张
[GUI] 正常退出
```

拖拽支持正常、模型走本地 `models/`（无下载动作）、输出图白底干净无彩边。

### 3) 性能对比（同一台 Win11 机器，同一批 3072×4096 素材）

| 场景 | 旧版（py3.13 / ORT 1.30） | 新版（py3.8 / ORT 1.14） | 差异 |
|---|---|---|---|
| 启动到模型就绪 | ~68s | ~70s | 基本持平 |
| u2net 连续 3 张 | 13s | 13s | 持平 |
| birefnet-general-lite 单张 | 14.9s | 19.2s | **慢约 29%** |

结论：日常用的「速度优先（u2net）」不受影响；「质量优先（BiRefNet）」慢约三成，
这是 ORT 从 1.30 降到 1.14 的必然代价。

---

## 六、与现代构建（Python 3.11+）的差异

| 项目 | 现代构建 | Win7 构建 |
|---|---|---|
| 界面 / 操作 / 输出参数 | — | **完全一致**（同一份 `whitebg/gui.py`） |
| 三个模型（u2net / birefnet-general-lite / birefnet-general） | 支持 | **全部支持**（实测前两个跑通） |
| 拖拽导入 | 支持 | 支持 |
| 边缘去色（decontaminate） | rembg 原生 | 手工复刻，效果一致 |
| 精细边缘（alpha_matting） | 支持 | 支持（需 pymatting JIT） |
| 目录结构 | PyInstaller 6（`_internal/` 子目录） | PyInstaller 5（**平铺**），文件数 2707 → 1420 |
| 体积 | 354MB | 349MB |
| 命令行 exe | 可打 | 同样可打，但**未随包提供**（`packaging/*.spec` 只配了 GUI；需要时加一份 `console=True` 的 spec 即可） |


---

## 七、已知限制 / 未验证项

1. **没有在真实 Win7 机器上跑过**。手头只有 Win11，验证手段是
   ①静态扫描全部 PE 依赖 ②Win11 上真实启动跑通。这两项能排掉 95% 的兼容坑，
   但真机首次运行仍建议看一眼 `启动日志.txt`。
2. Windows 8 / 8.1 未单独测试（理论上比 Win7 更宽松）。
3. 未做数字签名，SmartScreen 仍会拦一次，属正常。
4. BiRefNet 两个模型只实测了 `birefnet-general-lite`，`birefnet-general` 未单独跑。

---

## 八、出问题怎么查

在目标机按 `Win+R` 输入 `cmd`，执行：

```bat
winver
dir C:\Windows\System32\api-ms-win-crt-runtime-l1-1-0.dll
dir C:\Windows\System32\ucrtbase.dll
```

- 三条都在 → 环境没问题，看 `启动日志.txt`
- 后两条"找不到文件" → 缺 UCRT，装 `vc_redist.x64.exe`
- `winver` 显示 6.1.7600（没有 SP1）→ 先打 SP1

静态体检随时可复跑：

```bash
./.venv/Scripts/python.exe packaging/scan_win7.py dist_win7
```
