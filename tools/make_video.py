"""渲染 docs/demo.mp4：1280x720 / 30fps / 20s / 5 个镜头 + 配乐。

确定性渲染（不用 AI 文生视频）：每一帧都是 ``frame_at(t)`` 的纯函数，
同一时间点渲染多次结果完全一致，改文案不用重新"抽卡"。

用法::

    python tools/make_video.py            # 需要先跑 tools/make_bgm.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from whitebg import theme  # noqa: E402  配色和界面共用一套令牌

W, H = 1280, 720
FPS = 30
SCENE = 4.0                 # 每镜 4 秒
N_SCENES = 5
DUR = SCENE * N_SCENES      # 20.0s
XFADE = 0.0                 # 硬切。0.12s 的交叉淡入仍会留下明显的"双重曝光"残影

FONT_DIR = Path("C:/Windows/Fonts")
IMG_UI = ROOT / "docs" / "images" / "ui.png"
IMG_DONE = ROOT / "docs" / "images" / "ui-done.png"
IMG_BA = ROOT / "docs" / "images" / "before-after.jpg"
AUDIO = ROOT / "docs" / "assets" / "bgm.mp3"
OUT = ROOT / "docs" / "demo.mp4"


def font(size: int, bold: bool = True):
    name = "msyhbd.ttc" if bold else "msyh.ttc"
    return ImageFont.truetype(str(FONT_DIR / name), size)


def mono(size: int):
    return ImageFont.truetype(str(FONT_DIR / "consola.ttf"), size)


def ease(p: float) -> float:
    p = max(0.0, min(1.0, p))
    return 1 - (1 - p) ** 3


def base_canvas() -> Image.Image:
    return Image.new("RGB", (W, H), theme.BG)


def with_alpha(base: Image.Image, draw_fn, alpha: float) -> Image.Image:
    """把一段绘制以 alpha 叠到画面上（用于淡入）。"""
    if alpha <= 0:
        return base
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw_fn(ImageDraw.Draw(layer))
    if alpha < 1:
        layer.putalpha(layer.getchannel("A").point(lambda v: int(v * alpha)))
    return Image.alpha_composite(base.convert("RGBA"), layer).convert("RGB")


def paste_card(base: Image.Image, src: Image.Image, box, radius=14,
               shadow=True, frame=0) -> Image.Image:
    """把截图以圆角卡片形式贴上去，带柔和投影，可加一圈白色外框。

    加框是为了解决一个真实问题：应用截图自身的底色是 ``#F4F5F7``，
    和视频页面底色完全一样，不描一圈白边的话截图边缘会"消失"。
    """
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    ox0, oy0, ox1, oy1 = x0 - frame, y0 - frame, x1 + frame, y1 + frame

    if shadow:
        sh = Image.new("RGBA", base.size, (0, 0, 0, 0))
        ImageDraw.Draw(sh).rounded_rectangle(
            [ox0 + 2, oy0 + 8, ox1 + 2, oy1 + 12],
            radius=radius + frame, fill=(23, 33, 52, 52))
        sh = sh.filter(ImageFilter.GaussianBlur(12))
        base = Image.alpha_composite(base.convert("RGBA"), sh).convert("RGB")

    if frame:
        d = ImageDraw.Draw(base)
        d.rounded_rectangle([ox0, oy0, ox1, oy1], radius=radius + frame, fill="#FFFFFF")
        d.rounded_rectangle([ox0, oy0, ox1, oy1], radius=radius + frame,
                            outline=theme.BORDER, width=1)

    im = src.resize((w, h), Image.LANCZOS).convert("RGBA")
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=255)
    im.putalpha(mask)
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    layer.paste(im, (x0, y0), im)
    return Image.alpha_composite(base.convert("RGBA"), layer).convert("RGB")


def draw_pill(d: ImageDraw.ImageDraw, xy, text, fnt, fill, fg, pad_x=18, pad_y=10):
    x, y = xy
    tw = d.textlength(text, font=fnt)
    h = fnt.size + 2 * pad_y
    d.rounded_rectangle([x, y, x + tw + 2 * pad_x, y + h], radius=h / 2, fill=fill)
    d.text((x + pad_x, y + h / 2), text, font=fnt, fill=fg, anchor="lm")
    return tw + 2 * pad_x, h


# ───────────────────────────────────────────────────────────── 镜头
def scene1(p: float) -> Image.Image:
    """开场：标题 + 一句话 + 命令。"""
    im = base_canvas()
    a1 = ease((p - 0.00) / 0.35)
    a2 = ease((p - 0.10) / 0.35)
    a3 = ease((p - 0.20) / 0.35)
    dy = (1 - a1) * 10

    def draw(d):
        d.text((W / 2, 306 + dy), "白底图转换", font=font(78),
               fill=theme.INK, anchor="mm")
    im = with_alpha(im, draw, a1)

    def draw2(d):
        d.text((W / 2, 404), "拖进去，出来就是白底主图", font=font(30, False),
               fill=theme.INK_SUB, anchor="mm")
    im = with_alpha(im, draw2, a2)

    def draw3(d):
        f = mono(23)
        tw = d.textlength("python -m whitebg", font=f)
        bw, bh = tw + 44, 50
        x0, y0 = (W - bw) / 2, 468
        d.rounded_rectangle([x0, y0, x0 + bw, y0 + bh], radius=bh / 2, fill=theme.BRAND)
        d.text((W / 2, y0 + bh / 2), "python -m whitebg", font=f,
               fill="#FFFFFF", anchor="mm")
    im = with_alpha(im, draw3, a3)
    return im


def scene2(p: float) -> Image.Image:
    """前后对比：原图 → 白底主图，缓慢推近。"""
    im = base_canvas()

    def head(d):
        d.text((W / 2, 96), "一张随手拍的照片，变成能直接上架的主图",
               font=font(30, False), fill=theme.INK_SUB, anchor="mm")
    im = with_alpha(im, head, 1.0)

    src = Image.open(IMG_BA)
    scale = 1.0 + 0.04 * p                       # 1.00 → 1.04，绕中心推近
    bw0 = 840
    bh0 = int(bw0 * src.height / src.width)
    bw, bh = int(bw0 * scale), int(bh0 * scale)
    cx, cy = W // 2, 400
    x0, y0 = cx - bw // 2, cy - bh // 2
    im = paste_card(im, src, (x0, y0, x0 + bw, y0 + bh), radius=16)

    def note(d):
        d.text((W / 2, 678), "原图任意背景 · 输出 1200 × 1200 纯白底",
               font=font(24, False), fill=theme.INK_MUTE, anchor="mm")
    im = with_alpha(im, note, ease(p / 0.3))
    return im


def scene3(p: float) -> Image.Image:
    """主界面 + 三条卖点。"""
    im = base_canvas()
    slide = int((1 - ease(p / 0.35)) * 24)

    src = Image.open(IMG_UI)
    h = 520
    w = int(h * src.width / src.height)
    x0 = W - 84 - w + slide
    y0 = (H - h) // 2
    im = paste_card(im, src, (x0, y0, x0 + w, y0 + h), radius=12, frame=12)

    def left(d):
        d.text((92, 200), "批量处理", font=font(42), fill=theme.INK, anchor="lm")
        d.text((92, 248), "一整个文件夹丢进来就行", font=font(21, False),
               fill=theme.INK_MUTE, anchor="lm")
    im = with_alpha(im, left, ease((p - 0.05) / 0.3))

    items = ["拖拽整个文件夹", "两种模型随意切", "全程本地不联网"]
    for i, txt in enumerate(items):
        a = ease((p - 0.14 - i * 0.07) / 0.3)

        def draw(d, txt=txt, i=i):
            y = 320 + i * 74
            d.ellipse([94, y - 5, 104, y + 5], fill=theme.BRAND)
            d.text((124, y), txt, font=font(27, False), fill=theme.INK_SUB, anchor="lm")
        im = with_alpha(im, draw, a)
    return im


def scene4(p: float) -> Image.Image:
    """完成态：结果区高亮。"""
    im = base_canvas()

    src = Image.open(IMG_DONE)
    h = 520
    w = int(h * src.width / src.height)
    x0 = 76 + int((1 - ease(p / 0.35)) * 24)
    y0 = (H - h) // 2
    im = paste_card(im, src, (x0, y0, x0 + w, y0 + h), radius=12, frame=12)

    # 结果区聚光：把其余部分压一层淡色，只留结果区原色。
    # 刻意不画描边框——3px 的线会正好压在提示文字上，越描越糊。
    rx0, ry0 = x0 + int(w * 0.03), y0 + int(h * 0.745)
    rx1, ry1 = x0 + int(w * 0.97), y0 + int(h * 0.975)
    mask = Image.new("L", im.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([rx0, ry0, rx1, ry1], radius=12, fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(16))
    alpha = 0.82 * min(1.0, p / 0.35)            # 随镜头推进淡入，不要突兀
    veil = Image.new("RGBA", im.size, (244, 245, 247, 0))
    veil.putalpha(mask.point(lambda v: int(72 * alpha * (1 - v / 255))))
    im = Image.alpha_composite(im.convert("RGBA"), veil).convert("RGB")

    tx = x0 + w + 64

    def head(d):
        d.text((tx, 300), "跑完", font=font(38), fill=theme.INK, anchor="lm")
        d.text((tx, 352), "直接打开输出文件夹", font=font(38), fill=theme.BRAND, anchor="lm")
    im = with_alpha(im, head, ease((p - 0.1) / 0.3))

    def sub(d):
        d.text((tx, 424), "成功张数 · 耗时 · 输出路径", font=font(23, False),
               fill=theme.INK_MUTE, anchor="lm")
    im = with_alpha(im, sub, ease((p - 0.2) / 0.3))
    return im


def scene5(p: float) -> Image.Image:
    """收尾：标签 + 命令 + 仓库地址。"""
    im = base_canvas()

    def head(d):
        d.text((W / 2, 270), "开源 · MIT · 本地运行", font=font(46), fill=theme.INK,
               anchor="mm")
    im = with_alpha(im, head, 1.0)   # 硬切，进场即完整，不留空帧

    tags = ["rembg", "批量抠图", "ONNX 推理", "Windows 7 兼容"]
    f = font(22, False)
    widths = []
    tmp = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    for t in tags:
        widths.append(tmp.textlength(t, font=f) + 36)
    gap = 14
    total = sum(widths) + gap * (len(tags) - 1)
    x = (W - total) / 2
    for i, (t, tw) in enumerate(zip(tags, widths)):
        a = ease((p - i * 0.03) / 0.18)

        def draw(d, t=t, x=x, tw=tw):
            d.rounded_rectangle([x, 338, x + tw, 382], radius=22, fill=theme.BRAND_SOFT)
            d.text((x + tw / 2, 360), t, font=f, fill=theme.BRAND_INK, anchor="mm")
        im = with_alpha(im, draw, a)
        x += tw + gap

    def cmds(d):
        fm = mono(21)
        for i, line in enumerate(["git clone https://github.com/jimmyXiang123/whitebg.git",
                                  "pip install -r requirements.txt"]):
            d.text((W / 2, 450 + i * 42), line, font=fm, fill=theme.INK_SUB, anchor="mm")
    im = with_alpha(im, cmds, ease((p - 0.08) / 0.18))

    def url(d):
        d.text((W / 2, 570), "github.com/jimmyXiang123/whitebg", font=font(22, False),
               fill=theme.INK_MUTE, anchor="mm")
    im = with_alpha(im, url, ease((p - 0.14) / 0.18))
    return im


SCENES = [scene1, scene2, scene3, scene4, scene5]


# ───────────────────────────────────────────────────────────── 时间轴
def frame_at(t: float) -> Image.Image:
    i = min(int(t // SCENE), N_SCENES - 1)
    p = (t - i * SCENE) / SCENE
    im = SCENES[i](p)

    # 转场：默认硬切（XFADE=0）。切点落在音乐的和弦转换上，
    # 比交叉淡入更利落——两个版式完全不同的画面叠化时，
    # 大标题会残留在下一镜的截图上面，看起来像双重曝光。
    fade = XFADE / SCENE
    if XFADE > 0 and i < N_SCENES - 1 and p > 1 - fade:
        nxt = SCENES[i + 1](0.0)
        im = Image.blend(im, nxt, (p - (1 - fade)) / fade)

    # 全片首尾淡入淡出
    if t < 0.35:
        im = Image.blend(base_canvas(), im, t / 0.35)
    elif t > DUR - 0.6:
        im = Image.blend(im, base_canvas(), (t - (DUR - 0.6)) / 0.6)
    return im


def main() -> int:
    if not AUDIO.exists():
        print("缺少配乐，先跑 python tools/make_bgm.py")
        return 2
    import imageio_ffmpeg

    ff = imageio_ffmpeg.get_ffmpeg_exe()
    total = int(round(DUR * FPS))
    print(f"渲染 {total} 帧 → {OUT}")

    cmd = [
        ff, "-hide_banner", "-loglevel", "error", "-y",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
        "-i", str(AUDIO),
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-shortest",
        "-movflags", "+faststart", str(OUT),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    assert proc.stdin is not None
    for n in range(total):
        proc.stdin.write(frame_at(n / FPS).tobytes())
        if n % 120 == 0:
            print(f"  {n}/{total}")
    proc.stdin.close()
    code = proc.wait()
    if code != 0:
        print("ffmpeg 失败", code)
        return code
    print("完成", OUT, f"{OUT.stat().st_size / 1024 / 1024:.2f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
