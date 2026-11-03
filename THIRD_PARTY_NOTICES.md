# 第三方组件与许可证说明

本项目的**自有代码**采用 [MIT License](LICENSE)。但它站在一堆开源项目的肩膀上，
分发（尤其是**商用**）前请确认下面这些条款。本文只是便于自查的摘要，
以各项目官方仓库的 LICENSE 原文为准。

## 一、运行时依赖

| 组件 | 许可证 | 商用 | 备注 |
|---|---|---|---|
| [rembg](https://github.com/danielgatis/rembg) | MIT | ✅ | 抠图调度框架 |
| [ONNX Runtime](https://github.com/microsoft/onnxruntime) | MIT | ✅ | 推理引擎 |
| [PyMatting](https://github.com/pymatting/pymatting) | MIT | ✅ | 前景估计 / 精细蒙版 |
| [numpy](https://numpy.org) | BSD-3-Clause | ✅ | 需保留版权声明 |
| [Pillow](https://python-pillow.org) | MIT-CMU (HPND) | ✅ | 图像读写 |
| [scipy](https://scipy.org) | BSD-3-Clause | ✅ | 形态学处理 |
| [numba](https://numba.pydata.org) / [llvmlite](https://github.com/numba/llvmlite) | BSD-2-Clause | ✅ | JIT |
| [OpenCV](https://opencv.org)（`opencv-python-headless`） | Apache-2.0 | ✅ | rembg 的图像预处理 |
| [tkinterdnd2](https://github.com/pmgagne/tkinterdnd2) | MIT | ✅ | 拖拽支持 |
| [pooch](https://github.com/fatiando/pooch) / [tqdm](https://github.com/tqdm/tqdm) / [jsonschema](https://github.com/python-jsonschema/jsonschema) | BSD-3 / MPL-2.0+MIT / MIT | ✅ | rembg 的间接依赖 |
| Tcl/Tk（Python 自带 tkinter） | BSD-style | ✅ | 图形界面 |

## 二、模型权重（重点）

模型是**单独下载**的，不随本仓库分发，但它们各自有独立授权：

| 模型 | 许可证 | 商用 | 说明 |
|---|---|---|---|
| `u2net` / `u2netp` / `silueta` | Apache-2.0（U-2-Net） | ✅ | 需保留声明 |
| `birefnet-general` / `-lite` / `-portrait` 等 | MIT（BiRefNet） | ✅ | 作者明确允许商用 |
| `isnet-general-use` / `dis-*` | 见上游仓库 | ⚠️ 自行确认 | 部分版本仅限非商业 |
| `bria-rmbg`（RMBG-2.0） | **BRIA 商业授权** | ❌ 默认不可商用 | 商用需向 BRIA 购买授权 |

> 一句话建议：**做电商交付就用 `birefnet-general-lite` 或 `u2net`**，两者都是宽松许可；
> 不要在商用品里默认用 `bria-rmbg`。

## 三、打包相关

| 组件 | 许可证 | 说明 |
|---|---|---|
| [PyInstaller](https://pyinstaller.org) | GPL-2.0-or-later **WITH Bootloader exception** | 该例外条款明确允许把**打包产物**以任意许可证分发（包括闭源商用）。你分发的是 exe，不是 PyInstaller 本身，因此不受 GPL 传染 |

## 四、分发时的最低义务

1. 随包附上本文件与 [LICENSE](LICENSE)
2. 保留第三方组件的版权声明（打包时 PyInstaller 会把 `.dist-info` 一起带进产物）
3. 若替换或新增模型，自行核对该模型的授权
4. 本软件按 MIT 提供，**不附带任何担保**；把抠图结果用于商业宣传前，
   请自行确认素材与肖像权合规
