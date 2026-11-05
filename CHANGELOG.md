# 更新日志

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循语义化版本。

## [2.1.0] - 2026-11-05

### 变更

- **界面视觉重构**：新增 `whitebg/theme.py` 设计令牌（4pt 间距栅格、五级字号、三档圆角、
  单一强调色），`gui.py` 不再出现写死的色值与尺寸，改版只需动一个文件
- 按钮统一为 5 种变体（`primary` / `tonal` / `secondary` / `ghost` / `danger`）× 3 种尺寸，
  每种都有默认 / 悬停 / 禁用态；全页只保留一个主操作
- 卡片改为"两层极浅投影 + 1px 描边"，预览区内容按卡片高度撑满（此前只占顶部一条）
- 顶栏新增全局「打开输出文件夹」；输出规格（1200×1200 白底 JPG）标在预览区
- 缩略图末尾增加「继续添加」磁贴
- 窗口宽度小于 900 时切换紧凑布局：工具栏折行、外边距收紧、副标题隐藏

### 修复

- 次级文字 `#8E8E93`（3.4:1）与空状态提示 `#B0B0B8`（2.4:1）不满足 WCAG AA，
  统一改为 `#6E757F`（4.65:1）
- 缩略图透明区域被 Tk 渲染成黑框 —— 改为铺白底后按圆角遮罩裁切
- 缩略图改为居中裁切填满，一排图片宽窄一致
- 完成面板与状态行重复播报同一结果 —— 完成后由结果面板接管状态区
- 窄屏下结果文字被居中、按钮压到文字上方 —— 修正 pack 顺序，并给 Label 补 `anchor="w"`
- 图片不多时滚动条常驻 —— 内容放得下时自动收起
- 0% 的空进度条长期占位 —— 只在转换开始时出现
- 「模型」标签与下拉框的间距、下拉框只读态灰底

### 文档

- 新增 `docs/ui.md`：设计令牌、对比度复算脚本、组件变体表、断点与已知取舍
- 更新 README 中的界面截图

## [2.0.0] - 2026-11-03

### 变更

- **项目结构重构为可发布的 Python 包**：`white_bg_batch.py` / `gui_app.py` 合并为
  `whitebg` 包（`engine.py` / `gui.py`），支持 `pip install -e .`、`python -m whitebg`、
  `whitebg` / `whitebg-gui` 命令行入口
- 新增 `pyproject.toml`、`requirements*.txt`、`LICENSE`、`THIRD_PARTY_NOTICES.md`、
  `.gitignore`、CI 工作流
- 打包配置改为不依赖绝对路径（基于 `SPECPATH`），并整理为 `packaging/gui.spec`
  （Win10/11）与 `packaging/gui_win7.spec`（Win7）
- `base_dir()` 语义明确化：源码运行 = 仓库根目录，打包运行 = exe 目录

### 修复

- 本地没有 `models/` 时，不再强行把 `REMBG_HOME` 指到不可写的位置，
  改由 rembg 使用默认目录（`~/.u2net`）按需下载
- 输出路径过长时，会把右侧的「速度优先 / 质量优先 / 模型」整排挤出窗口 —— 路径标签改为定宽并只显示尾段
- 转换结束后「任务完成」面板被窗口高度裁掉：`RoundedFrame` 作为 Canvas 默认固定请求 265px，
  三张卡片叠加超过窗口高度，最后一张被裁 —— 改为高度跟随内容，预览区则允许收缩
- 模型下拉框与「模型」标签的左右顺序颠倒（显示成「u2net 模型」）
- `--help` 不再打印"正在启动/首次启动约 1 分钟"之类的启动横幅

### 文档

- **README 拆分为中英双语**：`README.md` 为英文版（GitHub 默认展示，也是 `pyproject.toml` 的 readme），
  `README.zh-CN.md` 为中文版，两份顶部各有语言切换入口
- README 新增「截图」章节（主界面 / 完成态 / 前后对比）与「涵盖的主题（Topics）」
- 新增 18 秒演示视频 `docs/demo.mp4`
- `CONTRIBUTING.md` 补充「两份 README 必须同步」的约定

### 移除

- 冗余的 `#!/usr/bin/env python`、`# -*- coding: utf-8 -*-`（Python 3 默认 UTF-8）
- 打包脚本里写死的本机绝对路径

## [1.4.0] - 2026-11-02

### 新增

- **Windows 7 兼容构建**：Python 3.8.20 + onnxruntime 1.14.1 + PyInstaller 5.13.2，
  详见 [docs/windows7.md](docs/windows7.md)
- `packaging/scan_win7.py`：扫描打包产物里是否残留 Win8+ 的 API 依赖

### 修复

- 打包时剔除构建机自带的 UCRT（`ucrtbase.dll` + 40 个 `api-ms-win-*`），
  改为使用目标机系统 UCRT，避免在 Win7 上加载失败
- 老版 rembg 不认 `REMBG_HOME`、也没有 `decontaminate` 参数，补上两条兼容路径

## [1.3.0] - 2026-11-01

### 新增

- 图形界面版：拖拽导入、圆角缩略图、胶囊进度条、模型一键切换、打开输出文件夹
- 边缘去色（去彩边），默认开启
- 打包脚本与便携版目录

## [1.2.0] - 2026-10-26

### 新增

- 自动裁到主体 + 统一留白比例
- 方图模式与精确 `N×N` 输出
- 可选柔和投影

## [1.0.0] - 2026-09-30

### 新增

- 首个版本：基于 rembg 的目录批量抠图 + 纯白底合成
