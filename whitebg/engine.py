"""批量把产品实拍图转成白底图（电商主图风格）的核心引擎。

底层抠图来自 `rembg`，本模块在其之上补齐了电商白底图真正需要的后处理：

* 纯白底合成（可直接输出 JPG 交付）
* 自动裁到主体并按比例留边，多张图构图统一
* 可选方图 + 精确尺寸（如统一 1200×1200）
* 可选柔和投影，避免"贴纸感"
* EXIF 方向自动校正（手机实拍图必备）
* 目录批处理、递归、跳过已存在、多进程加速

命令行用法::

    python -m whitebg -i input -o output
    python -m whitebg -i input -o output -m birefnet-general-lite --size 1200
    python -m whitebg -i input -o output --margin 0.12 --shadow
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from . import __version__

__all__ = [
    "IMAGE_EXTS",
    "MODEL_NOTES",
    "build_parser",
    "base_dir",
    "collect_inputs",
    "compose_on_white",
    "cutout_subject",
    "get_session",
    "init_runtime",
    "is_frozen",
    "log",
    "main",
    "process_one",
]


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}

MODEL_NOTES = {
    "birefnet-general": "BiRefNet 通用版，质量最好；MIT 协议可商用；速度偏慢",
    "birefnet-general-lite": "BiRefNet 轻量版，质量/速度平衡，推荐批量首选",
    "isnet-general-use": "ISNet 通用版，边缘干净、速度快，批量性价比高",
    "u2net": "U-2-Net 经典通用模型，最快，边缘略硬",
    "u2netp": "U-2-Net 精简版，最快但精度最低",
    "silueta": "U-2-Net 压缩版（43MB），速度接近 u2netp",
    "bria-rmbg": "BRIA RMBG-2.0（rembg 默认），质量很高，但商用需向 BRIA 付费授权",
    "birefnet-massive": "BiRefNet 大数据集版，质量高、体积大",
}


_LOG_FH = None


def log(msg: str) -> None:
    print(msg, flush=True)
    # 冻结版（exe）额外写一份日志到程序旁边，方便排查问题
    global _LOG_FH
    if is_frozen():
        try:
            if _LOG_FH is None:
                # utf-8-sig 带 BOM：保证记事本等工具一定能正确识别中文
                _LOG_FH = open(base_dir() / "启动日志.txt", "a", encoding="utf-8-sig")
            _LOG_FH.write(time.strftime("%H:%M:%S ") + msg + "\n")
            _LOG_FH.flush()
        except Exception:  # noqa: BLE001
            pass


_PACKAGE_DIR = Path(__file__).resolve().parent


def is_frozen() -> bool:
    """是否运行在 PyInstaller 打包出的 exe 里。"""
    return getattr(sys, "frozen", False)


def base_dir() -> Path:
    """工作根目录（models/、input/、output/ 都以它为基准）。

    * 打包运行：exe 所在目录，方便整个文件夹拷走即用
    * 源码运行：仓库根目录，即 ``whitebg/`` 的上一级
    """
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return _PACKAGE_DIR.parent


# --------------------------------------------------------------------------- #
# 抠图
# --------------------------------------------------------------------------- #
_SESSIONS: dict = {}
_LOCAL_MODELS_BOUND = False


def _bind_local_models() -> None:
    """把 rembg 的权重查找指向程序目录下的 models/。

    不同 rembg 版本找权重的方式不一样：
      * 新版（>=2.0.7x）认 REMBG_HOME，按 models/<名字>/<名字>.onnx 的子目录结构找；
      * 老版（Win7 兼容版用的 2.0.61）只认 U2NET_HOME 的平铺结构，找不到就联网下载。
    这里直接改写各会话类的 download_models：本地有对应权重就返回它，两个版本都能纯离线跑。
    """
    global _LOCAL_MODELS_BOUND
    if _LOCAL_MODELS_BOUND:
        return
    _LOCAL_MODELS_BOUND = True
    try:
        from rembg.sessions import sessions_class
    except Exception:  # noqa: BLE001
        return
    root = os.environ.get("REMBG_HOME") or ""
    if not root:
        return
    for cls in sessions_class:
        try:
            name = cls.name()
        except Exception:  # noqa: BLE001
            continue
        weight = Path(root) / "models" / name / f"{name}.onnx"
        if weight.is_file():
            cls.download_models = classmethod(lambda _cls, *a, _p=str(weight), **k: _p)


def get_session(model: str):
    """进程内复用同一个 session，避免重复加载模型。"""
    if model not in _SESSIONS:
        from rembg import new_session

        _bind_local_models()
        t0 = time.time()
        log(f"  [模型] 加载 {model}（首次使用会自动下载权重，请耐心等待）...")
        _SESSIONS[model] = new_session(model)
        log(f"  [模型] {model} 就绪，耗时 {time.time() - t0:.1f}s")
    return _SESSIONS[model]


def _supports_decontaminate(remove) -> bool:
    """rembg 是否原生支持 decontaminate 参数（2.0.8x 才有）。"""
    import inspect

    try:
        return "decontaminate" in inspect.signature(remove).parameters
    except Exception:  # noqa: BLE001
        return True


def _decontaminate_cutout(img, mask):
    """复刻新版 rembg 的前景去色：按 alpha 反推真实前景色，去掉软边残留的背景色。"""
    import numpy as np
    from PIL import Image
    from pymatting.foreground.estimate_foreground_ml import estimate_foreground_ml
    from pymatting.util.util import stack_images

    alpha = np.asarray(mask.convert("L")) / 255.0
    foreground = estimate_foreground_ml(np.asarray(img.convert("RGB")) / 255.0, alpha)
    cutout = np.clip(stack_images(foreground, alpha) * 255, 0, 255)
    return Image.fromarray(cutout.astype(np.uint8))


def cutout_subject(img, model: str, alpha_matting: bool, decontaminate: bool):
    """抠出主体，返回 RGBA 图像。"""
    from rembg import remove

    session = get_session(model)

    # 新版 rembg：原样调用（它能自己处理 decontaminate）
    if _supports_decontaminate(remove):
        return remove(
            img,
            session=session,
            alpha_matting=alpha_matting,
            decontaminate=decontaminate,
        ).convert("RGBA")

    # 老版 rembg（Win7 兼容版）：没有 decontaminate 参数，这里手工补上同样的效果。
    # 注意与 rembg 保持一致：alpha_matting（精细边缘）开启时去色会被忽略。
    if decontaminate and not alpha_matting:
        mask = remove(img, session=session, only_mask=True)
        return _decontaminate_cutout(img, mask).convert("RGBA")

    return remove(img, session=session, alpha_matting=alpha_matting).convert("RGBA")


# --------------------------------------------------------------------------- #
# 后处理
# --------------------------------------------------------------------------- #
def trim_to_subject(rgba, threshold: int = 12, margin: float = 0.0):
    """按 alpha 裁掉四周空白，再按最长边比例留出等量外边距。"""
    from PIL import Image

    alpha = rgba.getchannel("A").point(lambda v: 255 if v > threshold else 0)
    bbox = alpha.getbbox()
    if bbox is None:  # 全透明：没抠出主体，保持原样交给后续步骤
        return rgba
    subject = rgba.crop(bbox)
    if margin <= 0:
        return subject

    w, h = subject.size
    pad = int(round(max(w, h) * margin))
    canvas = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
    canvas.paste(subject, (pad, pad), subject)
    return canvas


def make_square(rgba, inner_margin: float = 0.0):
    """放进正方形画布居中，便于电商列表图统一构图。"""
    from PIL import Image

    w, h = rgba.size
    side = max(w, h)
    pad = int(round(side * inner_margin))
    total = side + pad * 2
    canvas = Image.new("RGBA", (total, total), (0, 0, 0, 0))
    canvas.paste(rgba, ((total - w) // 2, (total - h) // 2), rgba)
    return canvas


def fit_size(rgba, size: int, allow_upscale: bool = False):
    """等比缩放到最长边 = size。默认只缩不放（放大只会更糊）；
    小尺寸原图想要主体填满画布时用 --upscale 打开放大。"""
    from PIL import Image

    w, h = rgba.size
    longest = max(w, h)
    if longest == size:
        return rgba
    if longest > size or allow_upscale:
        scale = size / longest
        return rgba.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS)
    return rgba


def compose_on_white(rgba, shadow: bool = False, shadow_opacity: float = 0.28,
                     shadow_blur: float = 0.02, shadow_offset: float = 0.015):
    """把主体合成到纯白底上；可选加一层柔和投影。"""
    from PIL import Image, ImageFilter

    w, h = rgba.size
    white = Image.new("RGB", (w, h), (255, 255, 255))

    if shadow:
        alpha = rgba.getchannel("A")
        blur = max(1.0, max(w, h) * shadow_blur)
        soft = alpha.filter(ImageFilter.GaussianBlur(blur))
        if shadow_opacity < 1.0:
            soft = soft.point(lambda v: int(v * shadow_opacity))
        shadow_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        shadow_layer.putalpha(soft)
        dx = int(round(w * shadow_offset * 0.6))
        dy = int(round(h * shadow_offset))
        shifted = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        shifted.paste(shadow_layer, (dx, dy))
        white = Image.alpha_composite(white.convert("RGBA"), shifted).convert("RGB")

    white.paste(rgba, (0, 0), rgba)
    return white


def pad_to_exact(img, size: int, transparent: bool):
    """把画布精确补齐到 size x size，主体居中（此时已铺好底色/透明底）。"""
    from PIL import Image

    w, h = img.size
    if w == size and h == size:
        return img
    if transparent:
        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    else:
        canvas = Image.new("RGB", (size, size), (255, 255, 255))
    canvas.paste(img, ((size - w) // 2, (size - h) // 2), img if img.mode == "RGBA" else None)
    return canvas


def save_image(img, dst: Path, fmt: str, quality: int) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if fmt in ("jpg", "jpeg"):
        img.convert("RGB").save(dst, quality=quality, subsampling=0, optimize=True)
    elif fmt == "webp":
        img.save(dst, quality=quality, method=6)
    else:
        img.save(dst, optimize=True)


# --------------------------------------------------------------------------- #
# 单张处理
# --------------------------------------------------------------------------- #
def process_one(src: Path, dst: Path, args) -> float:
    from PIL import Image, ImageOps

    t0 = time.time()
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im)  # 手机实拍图方向校正
        rgba = cutout_subject(im.convert("RGBA"), args.model, args.alpha_matting,
                              not args.no_decontaminate)

    rgba = trim_to_subject(rgba, margin=args.margin)
    if args.square:
        rgba = make_square(rgba, inner_margin=args.inner_margin)
    if args.size:
        rgba = fit_size(rgba, args.size, allow_upscale=args.upscale)

    if args.transparent:
        final = rgba
    else:
        final = compose_on_white(rgba, shadow=args.shadow)

    # 方图 + 指定尺寸时，补齐到精确 N×N，保证一批图尺寸完全一致
    if args.size and args.square:
        final = pad_to_exact(final, args.size, args.transparent)

    save_image(final, dst, args.format, args.quality)
    return time.time() - t0


def _worker(payload):
    src, dst, args = payload
    try:
        return src, ("ok", process_one(Path(src), Path(dst), args))
    except Exception as exc:  # noqa: BLE001
        return src, ("fail", f"{type(exc).__name__}: {exc}")


def _init_worker(threads: int):
    """必须在 import onnxruntime 之前设置线程数才生效。"""
    if threads > 0:
        os.environ["OMP_NUM_THREADS"] = str(threads)


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #
def collect_inputs(inp: Path, recursive: bool) -> list:
    if inp.is_file():
        return [inp] if inp.suffix.lower() in IMAGE_EXTS else []
    pattern = "**/*" if recursive else "*"
    return sorted(p for p in inp.glob(pattern) if p.is_file() and p.suffix.lower() in IMAGE_EXTS)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="whitebg",
        description="批量把产品实拍图转成白底图（rembg 抠图 + 电商白底后处理）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="可用模型（-m 指定）：\n" + "\n".join(f"  {k:<24}{v}" for k, v in MODEL_NOTES.items()),
    )
    p.add_argument("-i", "--input", default="",
                   help="输入图片或目录；留空则用程序旁边的 input 文件夹")
    p.add_argument("-o", "--output", default="",
                   help="输出目录；留空则用程序旁边的 output 文件夹")
    p.add_argument("-m", "--model", default="birefnet-general-lite",
                   help="抠图模型，默认 birefnet-general-lite（实测对细结构最稳）")
    p.add_argument("-r", "--recursive", action="store_true", help="递归子目录")
    p.add_argument("--format", default=None, choices=["png", "jpg", "jpeg", "webp"],
                   help="输出格式；默认 jpg（透明底时自动 png）")
    p.add_argument("--quality", type=int, default=95, help="JPG/WebP 质量，默认 95")
    p.add_argument("--size", type=int, default=None,
                   help="输出边长上限像素；默认 1200（配合方图输出精确 1200×1200），0=不缩放")
    p.add_argument("--square", action="store_true", default=None, help="正方形画布（默认开）")
    p.add_argument("--no-square", dest="square", action="store_false", help="不要正方形画布，保持原宽高比")
    p.add_argument("--upscale", action="store_true",
                   help="小尺寸原图也放大到填满画布（默认只缩不放；放大可能发虚）")
    p.add_argument("--margin", type=float, default=0.06, help="主体四周留白比例，默认 0.06")
    p.add_argument("--inner-margin", type=float, default=0.04, help="方图模式额外内边距，默认 0.04")
    p.add_argument("--shadow", action="store_true", help="加柔和投影")
    p.add_argument("--transparent", action="store_true", help="输出透明底，不铺白底")
    p.add_argument("--alpha-matting", action="store_true", help="精细边缘（慢，适合毛发/毛绒/蕾丝）")
    p.add_argument("--no-decontaminate", action="store_true", help="关闭边缘去色污染（默认开启，能去彩色描边）")
    p.add_argument("--workers", type=int, default=1, help="并行进程数，默认 1")
    p.add_argument("--threads", type=int, default=0, help="每进程 ONNX 线程数，0=自动")
    p.add_argument("--overwrite", action="store_true", help="覆盖已存在的输出（默认跳过）")
    p.add_argument("--limit", type=int, default=0, help="只处理前 N 张（试跑用）")
    return p


def validate(args, parser) -> bool:
    if args.transparent and args.format in ("jpg", "jpeg"):
        parser.error("JPG 不支持透明通道：请去掉 --transparent，或改用 --format png/webp")
    if args.transparent and args.shadow:
        parser.error("--shadow 需要白底承载：请去掉 --transparent 或 --shadow")
    if args.margin < 0 or args.inner_margin < 0:
        parser.error("--margin / --inner-margin 不能为负数")
    if args.size is not None and args.size < 0:
        parser.error("--size 不能为负数")
    if args.workers < 1:
        parser.error("--workers 至少为 1")
    return True


def _resolve_model_root() -> Path | None:
    """定位本地权重目录（新版 rembg 布局：``<根>/models/models/<名字>/<名字>.onnx``）。

    找不到返回 None，交给 rembg 用默认目录（``~/.u2net``）按需联网下载。
    """
    for root in (base_dir() / "models", base_dir().parent / "models"):
        if (root / "models").is_dir():
            return root
    return None


def init_runtime() -> None:
    """进程级初始化：命令行与 GUI 版共用。必须在 import rembg 之前调用。"""
    import multiprocessing

    multiprocessing.freeze_support()

    # 权重优先用程序目录旁的 models/，不写系统盘（C 盘通常很紧张）。
    # rembg 在 import 时才读取这两个环境变量，这里设置是安全的。
    model_root = _resolve_model_root()
    if model_root is not None:
        os.environ.setdefault("REMBG_HOME", str(model_root))
        # 老版 rembg（2.0.6x，Win7 兼容版在用）只认 U2NET_HOME，一并指到同一目录
        os.environ.setdefault("U2NET_HOME", str(model_root))

    # 注：冻结环境下 numba 的磁盘缓存（@njit(cache=True)）会因找不到源码而崩溃，
    # 打 exe 前需把 pymatting 里的 cache=True 改成 cache=False（见 docs/build.md）；
    # 这里不需要 NUMBA_DISABLE_JIT，JIT 保持开启以保证边缘去色等算法速度。


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

    init_runtime()

    parser = build_parser()
    args = parser.parse_args(argv)  # --help / 参数错误在这里直接退出，不打启动横幅
    validate(args, parser)

    log(f"白底图转换 v{__version__} —— 开始处理")
    if is_frozen():
        log("提示：首次启动约需 1 分钟（解压运行环境 + 编译 + 加载模型），请耐心等待；")
        log("      运行时所有信息会同时写入程序旁的「启动日志.txt」")

    # 默认值解析：没显式指定输出选项时，统一出标准电商主图
    # （无参数双击 exe / 直接运行 = 1200×1200 白底 JPG；--transparent 则自动变透明 PNG 原尺寸）
    if args.square is None:
        args.square = not args.transparent
    if args.size is None:
        args.size = 1200 if args.square else 0
    if args.format is None:
        args.format = "png" if args.transparent else "jpg"

    # 双击 exe / 直接运行：没有任何参数 → 用程序旁的 input\output 并结束后停留
    interactive = not (args.input or args.output)

    def finish(code: int) -> int:
        if interactive:
            try:
                input("\n处理结束，按回车键关闭窗口 ...")
            except EOFError:  # stdin 被重定向时直接结束
                pass
        return code

    if is_frozen() and args.workers > 1:
        log("[提示] exe 版已禁用多进程（实测多进程反而更慢），workers 已强制为 1")
        args.workers = 1

    inp = Path(args.input).expanduser() if args.input else base_dir() / "input"
    out = Path(args.output).expanduser() if args.output else base_dir() / "output"
    if not inp.exists():
        log(f"[错误] 输入不存在：{inp}")
        return finish(2)

    files = collect_inputs(inp, args.recursive)
    if args.limit:
        files = files[: args.limit]
    if not files:
        log(f"[提示] {inp} 里没找到图片（支持：{', '.join(sorted(IMAGE_EXTS))}）")
        return finish(1)

    ext = "." + ("jpg" if args.format == "jpeg" else args.format)
    base = inp if inp.is_dir() else inp.parent

    jobs, skipped = [], 0
    for src in files:
        rel = src.relative_to(base) if inp.is_dir() else Path(src.name)
        dst = out / rel.with_suffix(ext)
        if dst.exists() and not args.overwrite:
            skipped += 1
            continue
        jobs.append((str(src), str(dst), args))

    log(f"[信息] 扫描到 {len(files)} 张，待处理 {len(jobs)} 张，跳过 {skipped} 张")
    log(f"[信息] 模型={args.model} 输出={out} 格式={ext} "
        f"底色={'透明' if args.transparent else '纯白'}"
        f"{' 方图' if args.square else ''}"
        f"{f' 最长边{args.size}px' if args.size else ''}"
        f"{' 投影' if args.shadow else ''}"
        f"{' 精细边缘' if args.alpha_matting else ''}")
    if not jobs:
        log("[信息] 没有需要处理的图片（如要重做请加 --overwrite）")
        return finish(0)

    workers = max(1, args.workers)
    if workers == 1:
        _init_worker(args.threads)
    else:
        per = args.threads if args.threads > 0 else max(1, (os.cpu_count() or 4) // workers)
        log(f"[信息] {workers} 进程并行，每进程 {per} 线程")

    # 先把模型下载/加载放在主进程里完成，避免多进程抢同一个权重文件
    get_session(args.model)

    t0 = time.time()
    ok = fail = 0
    log(f"[信息] 开始处理，共 {len(jobs)} 张\n")

    if workers == 1:
        for idx, (src, dst, a) in enumerate(jobs, 1):
            name = Path(src).name
            try:
                cost = process_one(Path(src), Path(dst), a)
                ok += 1
                log(f"  [{idx}/{len(jobs)}] {name}  OK  {cost:.1f}s")
            except Exception as exc:  # noqa: BLE001
                fail += 1
                log(f"  [{idx}/{len(jobs)}] {name}  FAIL  {type(exc).__name__}: {exc}")
    else:
        from concurrent.futures import ProcessPoolExecutor

        with ProcessPoolExecutor(max_workers=workers, initializer=_init_worker,
                                initargs=(per,)) as pool:
            for idx, (src, res) in enumerate(pool.map(_worker, jobs), 1):
                status, info = res
                if status == "ok":
                    ok += 1
                    log(f"  [{idx}/{len(jobs)}] {Path(src).name}  OK  {info:.1f}s")
                else:
                    fail += 1
                    log(f"  [{idx}/{len(jobs)}] {Path(src).name}  FAIL  {info}")

    dur = time.time() - t0
    log(f"\n[完成] 成功 {ok} 张，失败 {fail} 张，跳过 {skipped} 张；"
        f"耗时 {dur:.1f}s（平均 {dur / max(1, ok):.1f}s/张）")
    log(f"[输出] {out}")
    return finish(0 if fail == 0 else 3)


def launch() -> None:
    """命令行入口：统一兜底异常、写日志，打包成 exe 时额外弹窗提示。"""
    import traceback as _tb

    try:
        code = main()
    except SystemExit as exc:  # --help / 参数校验失败
        raise SystemExit(exc.code if isinstance(exc.code, int) else 1) from None
    except Exception as exc:  # noqa: BLE001
        trace = "".join(_tb.format_exception(type(exc), exc, exc.__traceback__))
        log("\n!! 程序运行出错，原因如下：\n")
        log(trace)
        if is_frozen():
            try:  # 弹窗提示，避免窗口一闪而过用户看不到错误
                import ctypes

                ctypes.windll.user32.MessageBoxW(
                    None,
                    f"白底图转换运行出错：\n\n{exc}\n\n"
                    f"完整错误信息已写入程序旁的「启动日志.txt」\n请把该文件内容发给技术人员。",
                    "白底图转换 - 错误",
                    0x10,
                )
            except Exception:  # noqa: BLE001
                pass
            try:
                input("\n按回车键关闭窗口 ...")
            except Exception:  # noqa: BLE001
                pass
        raise SystemExit(4) from None
    raise SystemExit(code)


if __name__ == "__main__":
    launch()
