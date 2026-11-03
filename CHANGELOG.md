# 更新日志

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循语义化版本。

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
- `--help` 不再打印"正在启动/首次启动约 1 分钟"之类的启动横幅

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
