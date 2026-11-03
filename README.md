# 白底图转换工具（whitebg）

把电商产品实拍图批量转成**白底主图**的本地小工具：`rembg` 负责抠图，本工具补上构图、留白、方图、
精确尺寸、柔和投影、边缘去色这些"交付级"后处理，图形界面和命令行都能用。

> 全程本地运行，图片不上传、不联网（首次下载模型除外）。

```
原图（任意背景）  ──▶  抠图  ──▶  裁到主体 + 留白  ──▶  方图/尺寸  ──▶  纯白底 / 透明底  ──▶  1200×1200 JPG
```

---

## 功能特性

- **批量处理**：整个文件夹丢进来，递归扫描、自动跳过已处理、可选多进程
- **两种入口**：Tkinter 图形界面（拖拽 + 缩略图预览 + 进度条）／命令行（可脚本化、可定时任务）
- **交付级后处理**：自动裁到主体、统一留白比例、方图、精确 `N×N` 像素、可选柔和投影
- **边缘去色**：按 alpha 反推前景色，去掉软边残留的背景色（彩边/光晕）
- **EXIF 方向校正**：手机竖拍图不会横过来
- **三种模型任选**：`u2net`（最快）／`birefnet-general-lite`（均衡，默认）／`birefnet-general`（最准）
- **可打包成免安装 exe**：含一份 Windows 7 兼容构建配置（见 [docs/windows7.md](docs/windows7.md)）

## 输出长什么样

默认（不加任何参数）就是标准电商主图：**1200×1200 白底 JPG**，主体居中、四周留白 6%、无投影。
需要别的口味时改参数即可：

| 想要 | 加的参数 |
|---|---|
| 透明底 PNG（后期自己排版） | `--transparent` |
| 保持原图宽高比，不做方图 | `--no-square` |
| 完全统一的 800×800 | `--size 800 --square` |
| 加一层柔和投影，避免"贴纸感" | `--shadow` |
| 毛绒 / 毛发 / 蕾丝，边缘要精细 | `--alpha-matting`（明显变慢） |

---

## 环境要求

| 项目 | 要求 |
|---|---|
| 操作系统 | Windows 10 / 11（64 位）。**Windows 7 请走 [docs/windows7.md](docs/windows7.md)** 的专用构建 |
| Python | 源码运行需 **3.11+**（`rembg 2.0.85` 的要求） |
| 内存 | 建议 8GB（大图 + 质量模型峰值约 2.5GB） |
| 磁盘 | 每个模型 40MB ~ 1GB，按需下载 |
| 网络 | 仅首次下载模型需要；之后可完全离线 |

## 安装

```bash
git clone https://github.com/jimmyXiang123/whitebg.git
cd whitebg

python -m venv .venv
.venv\Scripts\activate          # PowerShell / cmd
# source .venv/bin/activate     # macOS / Linux（未做测试）

pip install -r requirements.txt
```

> 首次运行时 `rembg` 会自动下载所选模型的权重。想离线部署的话，把权重放到
> `models/models/<模型名>/<模型名>.onnx` 即可，程序会优先用本地文件（不会联网）。

## 使用方法

### 图形界面

```bash
python -m whitebg
```

1. 把图片或文件夹**直接拖进窗口**，或点「＋ 添加图片 / 添加文件夹」
2. 选输出位置和模型（「速度优先」约 2~6 秒/张，「质量优先」约 15~20 秒/张）
3. 点「开始转换」，完成后点「打开输出文件夹」

首次打开会有 30~60 秒的模型加载等待（后台预热，进度条会显示"正在加载模型"），
之后每张图都是秒级。

### 命令行

```bash
# 最常用：整个文件夹 → 1200×1200 白底 JPG
python -m whitebg -i input -o output

# 透明底 PNG，保持原比例
python -m whitebg -i input -o output --transparent --format png --no-square

# 高质量模型 + 投影，先跑 5 张试水
python -m whitebg -i input -o output -m birefnet-general --shadow --limit 5
```

### 参数一览

| 参数 | 默认 | 说明 |
|---|---|---|
| `-i, --input` | `./input` | 输入图片或文件夹 |
| `-o, --output` | `./output` | 输出目录（自动创建，保留子目录结构） |
| `-m, --model` | `birefnet-general-lite` | 抠图模型，见下节 |
| `-r, --recursive` | 关 | 递归子目录 |
| `--format` | `jpg` | `png` / `jpg` / `jpeg` / `webp`；透明底时默认 png |
| `--quality` | `95` | JPG / WebP 质量 |
| `--size` | `1200` | 输出最长边像素，`0` = 不缩放 |
| `--square` / `--no-square` | 开 | 是否放进正方形画布 |
| `--upscale` | 关 | 小图也放大填满画布（默认只缩不放，避免发虚） |
| `--margin` | `0.06` | 主体四周留白比例 |
| `--inner-margin` | `0.04` | 方图模式额外的内边距 |
| `--shadow` | 关 | 加柔和投影（需白底，不能与 `--transparent` 同用） |
| `--transparent` | 关 | 输出透明底，不铺白底 |
| `--alpha-matting` | 关 | 精细边缘，适合毛发/毛绒/蕾丝，明显变慢 |
| `--no-decontaminate` | 关 | 关闭边缘去色（默认开启，能去掉彩边） |
| `--workers` | `1` | 并行进程数（实测单进程反而不抢内存，多数场景 1 最快） |
| `--threads` | `0` | 每个进程的 ONNX 线程数，`0` = 自动 |
| `--overwrite` | 关 | 覆盖已存在的输出（默认跳过） |
| `--limit` | `0` | 只处理前 N 张（试跑用） |

## 模型怎么选

| 模型 | 体积 | 速度 | 质量 | 授权 |
|---|---|---|---|---|
| `u2net` | 176MB | 最快（约 2~6 秒） | 边缘略硬 | Apache-2.0，可商用 |
| `birefnet-general-lite` | 224MB | 中（约 15~20 秒） | 细结构稳，**推荐批量首选** | MIT，可商用 |
| `birefnet-general` | 930MB | 慢 | 最准，复杂场景兜底 | MIT，可商用 |
| `bria-rmbg` | 176MB | 中 | 质量很高 | **商用需向 BRIA 付费授权** |
| `isnet-general-use` / `silueta` / `u2netp` | 小 | 快 | 各有短板（实测 isnet 会抠出矩形空洞） | 见各自仓库 |

> 实测结论：产品图（规整主体）用 `birefnet-general-lite` 最省心；纯白底小图用 `u2net` 更快。

## 打包成 exe（可选）

```bash
pip install -r requirements-build.txt
pyinstaller --noconfirm --clean --distpath dist --workpath build packaging/gui.spec
# 产物：dist/白底图转换GUI/ ，整个文件夹拷走即用
```

Windows 7 兼容版需要 Python 3.8 环境，步骤见 [docs/windows7.md](docs/windows7.md)，
打包后可用 `packaging/scan_win7.py` 做静态体检（是否残留 Win8+ 依赖）。

## 目录结构

```
.
├── whitebg/
│   ├── __init__.py        版本等元信息（不导入重依赖，import 是毫秒级）
│   ├── engine.py          转换引擎 + 命令行（PIL/rembg 只在函数内按需导入）
│   ├── gui.py             Tkinter 图形界面
│   └── __main__.py        python -m whitebg 的统一入口
├── run_gui.py             GUI 启动器（PyInstaller 打包指向这里）
├── run_cli.py             命令行启动器
├── packaging/
│   ├── gui.spec           Win10/11 打包配置
│   ├── gui_win7.spec      Win7 兼容打包配置
│   └── scan_win7.py       Win7 兼容性静态体检
├── tests/                 单元测试（不需要模型，CI 可跑）
├── docs/
│   ├── windows7.md        Win7 兼容版：依赖天花板、环境要求、验证记录
│   └── build.md           打包详解
├── requirements.txt       运行时依赖
├── requirements-win7.txt  Win7 构建的版本锁定
└── pyproject.toml         包元信息 / 入口脚本 / ruff 配置
```

`models/`、`input/`、`output/` 属于运行时数据，已在 `.gitignore` 里排除。

## 常见问题

**Q：输出 1200×1200 里主体偏小？**
默认"只缩不放"：小于画布的原图不会被强行放大（放大只会发虚）。加 `--upscale`，或直接用大尺寸原图。

**Q：边缘有彩色描边 / 光晕？**
原图背景色渗进了边缘（绿幕、蓝墙常见）。默认已开启去色污染；确认没有加 `--no-decontaminate`。

**Q：某张图抠坏了（空洞 / 糊成一片 / 多块残留）？**
模型各有短板。先换 `birefnet-general-lite` 或 `birefnet-general`，多数能解决；
毛发类再加 `--alpha-matting`。

**Q：`python -m whitebg` 打不开窗口？**
需要带 Tk 的 Python（python.org 官方安装包默认带上；conda 也带）。Linux 上要另装 `python3-tk`。

**Q：首次运行卡在"正在加载模型"？**
在下载权重，或是在做 JIT 编译，属正常现象。离线环境请预先把模型放到 `models/`。

**Q：为什么没有做成单文件 exe？**
单文件每次启动都要把上百 MB 解压到临时目录，老机器上又慢又容易被杀软拦。
文件夹版启动更快、更稳定，整个目录拷走一样能用。

## 开发

```bash
pip install -e . --no-deps       # 只装本包，跑测试不需要 rembg
python -m unittest discover -s tests -v
ruff check .                     # 可选，风格检查
```

CI（`.github/workflows/ci.yml`）在 Windows 上跑 Python 3.11 / 3.12 / 3.13 的单元测试，
不下载模型，几十秒出结果。

## 许可证

本项目代码采用 [MIT License](LICENSE)。
内置/依赖的第三方组件（rembg、ONNX Runtime、U-2-Net、BiRefNet、PyMatting、OpenCV、PyInstaller 等）
各自的许可证与商用注意事项见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

## 致谢

- [rembg](https://github.com/danielgatis/rembg) —— 抠图能力的地基
- [U-2-Net](https://github.com/xuebinqin/U-2-Net)、[BiRefNet](https://github.com/ZhengPeng7/BiRefNet) —— 模型
- [ONNX Runtime](https://github.com/microsoft/onnxruntime) —— 推理引擎
