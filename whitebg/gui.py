"""白底图转换工具 —— 图形界面版（iOS 风格：系统原生绘制，无在线资源依赖）。

功能：

* 按钮选择图片 / 选择文件夹，或直接把文件/文件夹拖进窗口
* 圆角缩略图预览，可逐张移除（✕）或一键清空，可继续追加
* 「开始转换」后台抠图，胶囊进度条实时显示
* 完成后提示输出位置，一键打开输出文件夹
* 所有运行信息同时写入程序旁的「启动日志.txt」

自测模式：设置环境变量 ``GUI_SMOKE=1`` 后启动，会自动处理 input 文件夹并自动退出。
"""

from __future__ import annotations

import math
import os
import queue
import sys
import threading
import time
import traceback as _tb
from pathlib import Path

from . import engine, theme

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD  # type: ignore
    HAVE_DND = True
except Exception:  # noqa: BLE001
    HAVE_DND = False

from PIL import Image, ImageDraw, ImageOps, ImageTk

APP_TITLE = "白底图转换工具"
THUMB = theme.THUMB
COLS = 6  # 兜底列数；实际列数由窗口宽度算出（见 _cols_for）
# 默认“速度优先”模型（约 2 秒/张），可一键切“质量优先”
MODELS = ["u2net", "birefnet-general-lite", "birefnet-general"]
SPEED_MODEL = "u2net"
QUALITY_MODEL = "birefnet-general-lite"
SMOKE = os.environ.get("GUI_SMOKE") == "1"

# ---------------------------------------------------------------------------
# 颜色取自 theme 令牌（唯一来源），这里保留短别名供历史代码引用
# ---------------------------------------------------------------------------
COL_BG = theme.BG
COL_CARD = theme.SURFACE
COL_TEXT = theme.INK
COL_SUB = theme.INK_MUTE     # 旧值 #8E8E93 只有 3.4:1，已换成过 AA 的 #6E757F
COL_ACCENT = theme.BRAND
COL_ACCENT_DARK = theme.BRAND_HOVER
COL_HOVER = theme.BRAND_SOFT
COL_TRACK = theme.SURFACE_ALT
COL_DANGER = theme.DANGER
COL_OK = theme.SUCCESS
COL_HINT = theme.INK_MUTE
RADIUS = theme.R_CARD
CARD_PAD = theme.CARD_PAD
WIN_W = theme.WIN_W
WIN_H = theme.WIN_H

F = theme.font


def round_rect_pts(x1, y1, x2, y2, r):
    return [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
            x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]


class RoundedFrame(tk.Canvas):
    """圆角卡片：两层极浅投影 + 1px 描边，内容放在 ``inner`` 里。

    ``autosize=True``（默认）高度跟随内容——Canvas 默认会"请求" 265px，
    三张卡片各占 265 就会把最后一张（含完成面板）顶出窗口；
    预览区这类需要撑满剩余空间的卡片传 ``autosize=False``，此时 inner 也会被
    撑到卡片高度（否则内容只占顶部一条，下面留一片空白）。
    """

    def __init__(self, master, radius=RADIUS, bg=COL_CARD, pad=CARD_PAD,
                 autosize=True, height=1, border=True, **kw):
        super().__init__(master, bg=COL_BG, highlightthickness=0, bd=0, height=height, **kw)
        self._radius, self._fill, self._pad = radius, bg, pad
        self._autosize = autosize
        self._border = border
        self.inner = tk.Frame(self, bg=bg)
        self._win = self.create_window(pad, pad, anchor="nw", window=self.inner)
        self.bind("<Configure>", self._redraw)
        if autosize:
            self.inner.bind("<Configure>", self._sync_height)
            # 首次布局时 inner 的 <Configure> 早于绑定发生，这里补一次同步
            self.after_idle(self._sync_height)

    def _sync_height(self, event=None) -> None:
        if not self._autosize:
            return
        h = event.height if event is not None else self.inner.winfo_reqheight()
        target = h + 2 * self._pad
        if target > 1 and target != int(self.cget("height")):
            self.configure(height=target)

    def _card_poly(self, x1, y1, x2, y2, fill, outline="") -> None:
        try:
            # 个别显卡/Tk 版本对 smooth 多边形渲染异常，兜底用普通矩形
            self.create_polygon(round_rect_pts(x1, y1, x2, y2, self._radius),
                                smooth=True, fill=fill, outline=outline, tags="card")
        except tk.TclError:
            self.create_rectangle(x1, y1, x2, y2, fill=fill, outline=outline, tags="card")

    def _redraw(self, _e=None):
        w, h = self.winfo_width(), self.winfo_height()
        if w < 20 or h < 20:
            return
        self.delete("card")
        # 先画两层投影（只有下缘露出来），再盖卡片本体
        self._card_poly(2, 4, w - 1, h - 1, theme.SHADOW_2)
        self._card_poly(2, 3, w - 1, h - 2, theme.SHADOW_1)
        self._card_poly(2, 2, w - 2, h - 2, self._fill,
                        outline=theme.BORDER if self._border else "")
        self.coords(self._win, self._pad, self._pad)
        try:
            self.itemconfigure(self._win, width=max(1, w - 2 * self._pad))
            if not self._autosize:
                self.itemconfigure(self._win, height=max(1, h - 2 * self._pad))
        except tk.TclError:
            pass


# 按钮变体：一个页面只有一种主色，其余靠底色/描边分层
BUTTON_VARIANTS = {
    "primary": dict(bg=theme.BRAND, fg="#FFFFFF", hover=theme.BRAND_HOVER,
                    bold=True, ring=False),
    "tonal": dict(bg=theme.BRAND_SOFT, fg=theme.BRAND_INK, hover=theme.BRAND_SOFT_HOVER,
                  bold=True, ring=False),
    "secondary": dict(bg=theme.SURFACE, fg=theme.INK, hover=theme.SURFACE_ALT,
                      bold=False, ring=True),
    "ghost": dict(bg=None, fg=theme.INK_SUB, hover=theme.SURFACE_ALT,
                  bold=False, ring=False),
    "danger": dict(bg=None, fg=theme.DANGER, hover=theme.DANGER_SOFT,
                   bold=False, ring=False),
}
BTN_SIZES = {
    "sm": (theme.F_LABEL, 12, 5),
    "md": (theme.F_BODY, 16, 7),
    "lg": (theme.F_CTA, 18, 12),
}


class Button(tk.Button):
    """统一按钮：变体 + 尺寸 + 悬停/禁用状态。

    仍然用原生 tk.Button 渲染（不画 Canvas）：早期在部分显卡/老 Tk 上自绘按钮
    会出黑块，原生控件最稳。圆角拿不到，就用统一的边框、内边距和配色来建立
    系统感——视觉一致性靠"节奏"而不是靠描边特效。
    """

    def __init__(self, master, text, command=None, variant="secondary", size="md",
                 bold=None, **kw):
        spec = BUTTON_VARIANTS[variant]
        try:
            parent_bg = master.cget("bg")
        except Exception:  # noqa: BLE001  ttk 控件没有 bg
            parent_bg = theme.SURFACE
        base_bg = spec["bg"] or parent_bg
        fsize, padx, pady = BTN_SIZES.get(size, BTN_SIZES["md"])
        super().__init__(
            master, text=text, command=command,
            font=theme.font(fsize, spec["bold"] if bold is None else bold),
            bg=base_bg, fg=spec["fg"],
            activebackground=spec["hover"], activeforeground=spec["fg"],
            relief="flat", bd=0, cursor="hand2", takefocus=True,
            padx=padx, pady=pady,
            highlightthickness=1 if spec["ring"] else 0,
            highlightbackground=theme.BORDER_STRONG if spec["ring"] else base_bg,
            highlightcolor=theme.BRAND,
            **kw)
        self._spec = spec
        self._base_bg = base_bg
        self._enabled = True
        self.bind("<Enter>", self._on_enter, add="+")
        self.bind("<Leave>", self._on_leave, add="+")

    def _on_enter(self, _e=None):
        if self._enabled:
            self.configure(bg=self._spec["hover"])

    def _on_leave(self, _e=None):
        if self._enabled:
            self.configure(bg=self._base_bg)

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        if enabled:
            self.configure(state="normal", bg=self._base_bg, fg=self._spec["fg"],
                           cursor="hand2")
        else:
            self.configure(state="disabled", bg=theme.SURFACE_ALT,
                           fg=theme.INK_DISABLED, cursor="arrow")

    def set_variant(self, variant: str) -> None:
        """切换变体（用于「速度优先 / 质量优先」这类互斥选项的选中态）。"""
        spec = BUTTON_VARIANTS[variant]
        try:
            parent_bg = self.master.cget("bg")
        except Exception:  # noqa: BLE001
            parent_bg = theme.SURFACE
        self._spec = spec
        self._base_bg = spec["bg"] or parent_bg
        self.configure(bg=self._base_bg, fg=spec["fg"],
                       activebackground=spec["hover"],
                       highlightthickness=1 if spec["ring"] else 0,
                       highlightbackground=(theme.BORDER_STRONG if spec["ring"]
                                            else self._base_bg))


# 兼容旧名字（打包脚本/外部代码可能引用过 iOSButton）
iOSButton = Button


class RoundedProgress(tk.Canvas):
    """胶囊进度条，宽度跟随容器。"""

    def __init__(self, master, height=8, radius=4):
        super().__init__(master, height=height, bg=COL_CARD,
                         highlightthickness=0, bd=0)
        self._ph, self._pr = height, radius
        self._frac = 0.0
        self.bind("<Configure>", lambda e: self._draw())
        self._draw()

    def _bar(self, x1, x2, fill):
        if x2 - x1 < 1:
            return
        r = min(self._pr, (x2 - x1) / 2, self._ph / 2)
        try:
            self.create_polygon(round_rect_pts(x1, 0, x2, self._ph, r),
                                smooth=True, fill=fill)
        except tk.TclError:  # 渲染兼容性兜底
            self.create_rectangle(x1, 0, x2, self._ph, fill=fill)

    def _draw(self):
        w = self.winfo_width()
        if w < 10:
            w = 320  # 首次布局前给个占位宽度
        self.delete("all")
        self._bar(0, w, theme.BORDER_STRONG)  # 轨道要看得见，否则空进度像一条毛边
        fw = w * self._frac
        if fw > 1:
            self._bar(0, fw, COL_ACCENT)

    def set(self, frac: float):
        self._frac = max(0.0, min(1.0, frac))
        self._draw()


def load_thumb(path: Path, size: int = THUMB, radius: int = theme.R_THUMB) -> Image.Image:
    """后台线程用：只做纯 PIL 处理（不碰 Tk），返回圆角方图。

    两点讲究：
    * 不做"完整放进方框"（会留白边，每格宽窄不一），改成居中裁切填满，
      一排缩略图才有整齐的节奏；
    * 不能直接给 RGBA —— Tk 不做 alpha 混合，透明像素会显示成黑块（缩略图
      四边那种"黑框"就是这么来的）。铺白底后再按圆角遮罩裁切。
    """
    im = Image.open(path).convert("RGB")
    im = ImageOps.fit(im, (size, size), Image.LANCZOS, centering=(0.5, 0.5))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1],
                                           radius=radius, fill=255)
    out = Image.new("RGB", (size, size), (255, 255, 255))
    out.paste(im, (0, 0), mask)
    return out


def _thumb_to_photo(im: Image.Image | None) -> ImageTk.PhotoImage | None:
    """主线程专用：把 PIL 图转成 PhotoImage（Tk 只能在主线程操作）。"""
    return ImageTk.PhotoImage(im) if im is not None else None


def _fmt_sec(sec: float) -> str:
    """把秒数格式化成"5分20秒"之类的人类可读文本。"""
    sec = max(0, int(sec))
    m, s = divmod(sec, 60)
    return f"{m}分{s}秒" if m else f"{s}秒"


# ---------------------------------------------------------------------------
# 主应用
# ---------------------------------------------------------------------------
class WhiteBgApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.files: list[Path] = []
        self._seen: set[Path] = set()
        self.thumbs: dict[str, ImageTk.PhotoImage] = {}
        self.busy = False
        self.finished = False
        self.events: "queue.Queue" = queue.Queue()
        self._thumb_queue: "queue.Queue" = queue.Queue()
        self._preview_gen = 0
        self._model_lock = threading.Lock()
        self._model_ready = False
        self._animating = False
        self._loading = False
        self._base_frac = 0.0
        self._convert_start = 0.0
        self._buttons: list[iOSButton] = []
        self.model_var = tk.StringVar(value=SPEED_MODEL)
        # 默认输出位置：GUI 集成在工具根目录内时用根目录 output\；单独拷贝用自己旁边
        _tool = engine.base_dir()
        if (_tool.parent / "input").exists():
            _tool = _tool.parent
        self.out_dir = _tool / "output"
        self._build_ui()
        if HAVE_DND:
            # 拖拽注册到根窗口 + 所有可见区域，确保拖到哪里都能识别
            for w in self._drop_widgets:
                try:
                    w.drop_target_register(DND_FILES)
                    w.dnd_bind("<<Drop>>", self._on_drop)
                except Exception as exc:  # noqa: BLE001
                    engine.log(f"[拖拽] {w} 注册失败：{exc}")
        self.root.after(100, self._poll)
        self.root.after(1500, self._warmup)  # 后台预热模型，转换零等待

    @staticmethod
    def _short_path(path: Path, limit: int = 44) -> str:
        """路径太长时只显示尾段，避免把同一行的其它控件挤出窗口。"""
        text = str(path)
        return text if len(text) <= limit else "…" + text[-(limit - 1):]

    def _btn(self, parent, text, command=None, variant="secondary", size="md",
             bold=None, **kw):
        b = Button(parent, text, command=command, variant=variant, size=size,
                   bold=bold, **kw)
        self._buttons.append(b)
        return b

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        self.root.configure(bg=theme.BG)
        self.root.title(APP_TITLE)
        self.root.geometry(f"{WIN_W}x{WIN_H}")
        self.root.minsize(theme.WIN_MIN_W, theme.WIN_MIN_H)
        if not SMOKE:
            self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._compact = False
        self._cols = COLS

        self.outer = tk.Frame(self.root, bg=theme.BG)
        self.outer.pack(fill=tk.BOTH, expand=True,
                        padx=theme.GUTTER, pady=(theme.S5, theme.S6))

        # ── 顶部：标题 + 全局操作 ───────────────────────────────────
        head = tk.Frame(self.outer, bg=theme.BG)
        head.pack(fill=tk.X, pady=(0, theme.S4))
        self._btn(head, "打开输出文件夹", self.open_output,
                  variant="secondary", size="sm").pack(side=tk.RIGHT, pady=(theme.S1, 0))

        titles = tk.Frame(head, bg=theme.BG)
        titles.pack(side=tk.LEFT, anchor="w")
        tk.Label(titles, text=APP_TITLE, bg=theme.BG, fg=theme.INK,
                 font=F(theme.F_TITLE, True)).pack(anchor="w")
        self.subtitle = tk.Label(titles, text="批量抠图 · 白底电商主图 · 全程本地运行",
                                 bg=theme.BG, fg=theme.INK_MUTE, font=F(theme.F_LABEL))
        self.subtitle.pack(anchor="w", pady=(theme.S1, 0))

        # ── 卡片 1：素材 ────────────────────────────────────────────
        card1 = RoundedFrame(self.outer)
        card1.pack(fill=tk.X)
        c1 = card1.inner

        row1 = tk.Frame(c1, bg=theme.SURFACE)
        row1.pack(fill=tk.X)
        # 「添加图片」用 tonal：比相邻按钮更醒目，但不与底部主按钮争第一焦点
        self._btn(row1, "＋ 添加图片", self.add_files, variant="tonal").pack(side=tk.LEFT)
        self._btn(row1, "添加文件夹", self.add_folder,
                  variant="secondary").pack(side=tk.LEFT, padx=(theme.S2, 0))
        self._btn(row1, "清空", self.clear_all,
                  variant="ghost").pack(side=tk.LEFT, padx=(theme.S1, 0))
        self.count_label = tk.Label(row1, text="已选 0 张图片", bg=theme.SURFACE,
                                    fg=theme.INK_MUTE, font=F(theme.F_LABEL))
        self.count_label.pack(side=tk.RIGHT)

        tk.Frame(c1, bg=theme.BORDER, height=1).pack(fill=tk.X, pady=theme.S3)

        # 输出位置 + 模型：宽屏排一行，窄屏折成两行（见 _layout_toolbar）
        self.toolbar = tk.Frame(c1, bg=theme.SURFACE)
        self.toolbar.pack(fill=tk.X)

        self.tb_left = tk.Frame(self.toolbar, bg=theme.SURFACE)
        tk.Label(self.tb_left, text="输出位置", bg=theme.SURFACE, fg=theme.INK_MUTE,
                 font=F(theme.F_LABEL)).pack(side=tk.LEFT)
        # 路径锚定左侧并限制字符数：路径过长时只显示尾段，避免把右侧控件挤飞
        self.out_label = tk.Label(self.tb_left, text=self._short_path(self.out_dir),
                                  bg=theme.SURFACE, fg=theme.INK_SUB,
                                  font=F(theme.F_LABEL), anchor="w")
        self.out_label.pack(side=tk.LEFT, padx=(theme.S2, 0))
        self._btn(self.tb_left, "更改", self.choose_output,
                  variant="ghost", size="sm").pack(side=tk.LEFT, padx=(theme.S1, 0))

        self.tb_right = tk.Frame(self.toolbar, bg=theme.SURFACE)
        style = ttk.Style()
        style.theme_use("clam")
        # readonly 态的 ComboBox 走 background 而不是 fieldbackground，
        # 只配 fieldbackground 会得到一块灰底——这里两个都配，并显式映射只读态
        style.configure("IOS.TCombobox", fieldbackground=theme.SURFACE,
                        background=theme.SURFACE, foreground=theme.INK,
                        arrowcolor=theme.INK_SUB, bordercolor=theme.BORDER_STRONG,
                        lightcolor=theme.BORDER_STRONG, darkcolor=theme.BORDER_STRONG,
                        relief="flat", padding=5)
        style.map("IOS.TCombobox",
                  fieldbackground=[("readonly", theme.SURFACE)],
                  background=[("readonly", theme.SURFACE)],
                  foreground=[("readonly", theme.INK)],
                  selectbackground=[("readonly", theme.SURFACE)],
                  selectforeground=[("readonly", theme.INK)])
        # 下拉列表（Listbox）的配色不在 ttk 里，只能走 option 数据库
        self.root.option_add("*TCombobox*Listbox.background", theme.SURFACE)
        self.root.option_add("*TCombobox*Listbox.foreground", theme.INK)
        self.root.option_add("*TCombobox*Listbox.selectBackground", theme.BRAND_SOFT)
        self.root.option_add("*TCombobox*Listbox.selectForeground", theme.BRAND_INK)
        self.root.option_add("*TCombobox*Listbox.borderWidth", 0)
        self.model_box = ttk.Combobox(self.tb_right, textvariable=self.model_var,
                                      values=MODELS, state="readonly", width=21,
                                      style="IOS.TCombobox", font=F(theme.F_LABEL))
        self.model_label = tk.Label(self.tb_right, text="模型", bg=theme.SURFACE,
                                    fg=theme.INK_MUTE, font=F(theme.F_LABEL))
        # 速度/质量是互斥选项：做成胶囊组，选中态用 tonal 底、未选用 ghost
        self.model_btns = {
            SPEED_MODEL: self._btn(
                self.tb_right, "速度优先",
                lambda: self._set_model(SPEED_MODEL, "速度优先（u2net，约 2 秒/张）"),
                variant="tonal", size="sm"),
            QUALITY_MODEL: self._btn(
                self.tb_right, "质量优先",
                lambda: self._set_model(QUALITY_MODEL, "质量优先（birefnet-lite，约 10 秒/张）"),
                variant="ghost", size="sm"),
        }
        self._layout_toolbar(False)

        # ── 卡片 2：预览（expand 撑满，不跟随内容，否则图片一多就把底栏顶飞）──
        card2 = RoundedFrame(self.outer, autosize=False, height=120)
        card2.pack(fill=tk.BOTH, expand=True, pady=(theme.S3, 0))
        c2 = card2.inner

        head2 = tk.Frame(c2, bg=theme.SURFACE)
        head2.pack(fill=tk.X, pady=(0, theme.S2))
        tk.Label(head2, text="预览", bg=theme.SURFACE, fg=theme.INK,
                 font=F(theme.F_SECTION, True)).pack(side=tk.LEFT)
        self.preview_meta = tk.Label(head2, text="输出 1200 × 1200 · 白底 JPG",
                                     bg=theme.SURFACE, fg=theme.INK_MUTE,
                                     font=F(theme.F_LABEL))
        self.preview_meta.pack(side=tk.RIGHT)

        body = tk.Frame(c2, bg=theme.SURFACE)
        body.pack(fill=tk.BOTH, expand=True)
        # height 给小值：Canvas 默认 265px 的"请求高度"会把卡片3（含完成面板）顶出窗口
        self._sb_shown, self._syncing = True, False
        self.canvas = tk.Canvas(body, bg=theme.SURFACE, highlightthickness=0, bd=0, height=150)
        style.configure("IOS.Vertical.TScrollbar", background=theme.BORDER_STRONG,
                        troughcolor=theme.SURFACE, bordercolor=theme.SURFACE,
                        lightcolor=theme.BORDER_STRONG, darkcolor=theme.BORDER_STRONG,
                        arrowcolor=theme.INK_MUTE, relief="flat", arrowsize=10, width=9)
        self._vsb = ttk.Scrollbar(body, orient=tk.VERTICAL, command=self.canvas.yview,
                                  style="IOS.Vertical.TScrollbar")
        self.canvas.configure(yscrollcommand=self._vsb.set)
        self._vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._grid = tk.Frame(self.canvas, bg=theme.SURFACE)
        self._gwin = self.canvas.create_window((0, 0), anchor="nw", window=self._grid)
        self._grid.bind("<Configure>", self._on_grid_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind_all("<MouseWheel>",
                             lambda e: self.canvas.yview_scroll(int(-e.delta / 120), "units"))

        # 空状态：一句主提示 + 一句格式说明，替代原来两行同号的灰字
        self.hint = tk.Frame(body, bg=theme.SURFACE)
        tk.Label(self.hint, text="把图片拖到这里", bg=theme.SURFACE, fg=theme.INK_SUB,
                 font=F(theme.F_SECTION)).pack()
        tk.Label(self.hint, text="或点击上方「添加图片」· 支持 JPG / PNG / WEBP / BMP / TIF",
                 bg=theme.SURFACE, fg=theme.INK_MUTE,
                 font=F(theme.F_LABEL)).pack(pady=(theme.S2, 0))
        self._show_hint()

        # ── 卡片 3：操作 ────────────────────────────────────────────
        card3 = RoundedFrame(self.outer)
        card3.pack(fill=tk.X, pady=(theme.S3, 0))
        c3 = card3.inner

        # 全页唯一的主操作
        self.start_btn = self._btn(c3, "开始转换", self.start_convert,
                                   variant="primary", size="lg")
        self.start_btn.pack(fill=tk.X)

        # 进度条平时不占位：0% 的空条没有信息量，只在真的要跑的时候出现
        self.progress = RoundedProgress(c3, height=8)
        self.status_label = tk.Label(c3, text="请先添加要转换的图片", bg=theme.SURFACE,
                                     fg=theme.INK_MUTE, font=F(theme.F_LABEL),
                                     anchor="w", justify=tk.LEFT)
        self.status_label.pack(fill=tk.X, pady=(theme.S4, 0))

        # 完成面板
        self.done_frame = tk.Frame(c3, bg=theme.SURFACE)
        self.done_row = tk.Frame(self.done_frame, bg=theme.SURFACE)
        self.done_row.pack(fill=tk.X, pady=(theme.S3, 0))
        self.done_msg = tk.Label(self.done_row, text="", bg=theme.SURFACE, fg=COL_OK,
                                 font=F(theme.F_BODY, True), justify=tk.LEFT,
                                 anchor="w", wraplength=620)
        self.done_msg.pack(side=tk.LEFT, anchor="w")
        self.open_btn = self._btn(self.done_row, "打开输出文件夹", self.open_output,
                                  variant="secondary", size="sm")
        self.open_btn.pack(side=tk.LEFT, padx=(theme.S3, 0))
        self.fail_msg = tk.Label(self.done_frame, text="", bg=theme.SURFACE, fg=theme.DANGER,
                                 font=F(theme.F_LABEL), justify=tk.LEFT,
                                 anchor="w", wraplength=800)
        self.fail_msg.pack(anchor="w", pady=(theme.S2, 0))

        # 拖拽目标覆盖：根窗口 + 预览区及其子件
        self._drop_widgets = [self.root, self.outer, c2, body, self.canvas,
                              self._grid, self.hint]

        # 窗口尺寸变化 → 切换密度 / 重排列数
        self.root.bind("<Configure>", self._on_resize, add="+")

    # ---------------------------------------------------------- 响应式
    def _layout_toolbar(self, compact: bool) -> None:
        """输出位置与模型控件：宽屏一行左右分置，窄屏折成上下两行。"""
        for w in (self.tb_left, self.tb_right):
            w.pack_forget()
        kids = [self.model_btns[SPEED_MODEL], self.model_btns[QUALITY_MODEL],
                self.model_label, self.model_box]
        for w in kids:
            w.pack_forget()
        if compact:
            # 窄屏：速度/质量靠左，模型选择靠右，一行两簇，不浪费整行
            self.tb_left.pack(fill=tk.X)
            self.tb_right.pack(fill=tk.X, pady=(theme.S2, 0))
            self.model_btns[SPEED_MODEL].pack(side=tk.LEFT)
            self.model_btns[QUALITY_MODEL].pack(side=tk.LEFT, padx=(theme.S1, 0))
            self.model_box.pack(side=tk.RIGHT)
            self.model_label.pack(side=tk.RIGHT, padx=(0, theme.S1))
        else:
            self.tb_left.pack(side=tk.LEFT)
            self.tb_right.pack(side=tk.RIGHT)
            self.model_box.pack(side=tk.RIGHT)
            self.model_label.pack(side=tk.RIGHT, padx=(0, theme.S1))
            self.model_btns[QUALITY_MODEL].pack(side=tk.RIGHT, padx=(0, theme.S3))
            self.model_btns[SPEED_MODEL].pack(side=tk.RIGHT, padx=(0, theme.S2))

    def _on_resize(self, event) -> None:
        if event.widget is not self.root:
            return
        compact = event.width < theme.BREAKPOINT
        if compact != self._compact:
            self._compact = compact
            self._apply_density(compact)
            self._layout_toolbar(compact)
            self._layout_done(compact)
        cols = self._cols_for(event.width)
        if cols != self._cols:
            self._cols = cols
            self._relayout_grid()
        self.done_msg.configure(wraplength=max(280, event.width - 320))
        self.fail_msg.configure(wraplength=max(280, event.width - 120))

    def _apply_density(self, compact: bool) -> None:
        pad = theme.S4 if compact else theme.S5
        self.outer.pack_configure(padx=theme.S4 if compact else theme.GUTTER,
                                  pady=(pad, pad))
        if compact:
            self.subtitle.pack_forget()
        else:
            self.subtitle.pack(anchor="w", pady=(theme.S1, 0))

    def _layout_done(self, compact: bool) -> None:
        """完成面板：窄屏时按钮换到下一行，避免把提示文字压成两三个字一行。"""
        for w in (self.done_msg, self.open_btn):
            w.pack_forget()
        if compact:
            self.done_msg.pack(anchor="w", fill=tk.X)
            self.open_btn.pack(anchor="w", pady=(theme.S2, 0))
        else:
            self.done_msg.pack(side=tk.LEFT, anchor="w")
            self.open_btn.pack(side=tk.LEFT, padx=(theme.S3, 0))

    @staticmethod
    def _cols_for(width: int) -> int:
        """按可用宽度算缩略图列数：窗口越宽排得越多，最少 2 列。"""
        avail = width - 2 * theme.GUTTER - 2 * theme.CARD_PAD
        cols = int(avail // (THUMB + 14))
        return max(2, min(10, cols))

    def _relayout_grid(self) -> None:
        for i, card in enumerate(self._grid.winfo_children()):
            card.grid_configure(row=i // self._cols, column=i % self._cols,
                                padx=6, pady=6)

    def _show_hint(self) -> None:
        self.hint.place(relx=0.5, rely=0.5, anchor=tk.CENTER)

    def _on_grid_configure(self, _e=None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self._sync_scrollbar()

    def _on_canvas_configure(self, e) -> None:
        self.canvas.itemconfigure(self._gwin, width=e.width)
        self._sync_scrollbar()

    def _sync_scrollbar(self) -> None:
        """图片少到不需要滚动时收起滚动条，避免一条常驻的灰色竖条破坏版面。"""
        if self._syncing:
            return
        self._syncing = True
        try:
            need = self._grid.winfo_reqheight() > self.canvas.winfo_height() + 12
            if need == self._sb_shown:
                return
            self._sb_shown = need
            if need:
                self._vsb.pack(side=tk.RIGHT, fill=tk.Y, before=self.canvas)
            else:
                self._vsb.pack_forget()
        finally:
            self._syncing = False

    def _sync_model_buttons(self) -> None:
        cur = self.model_var.get()
        for name, btn in self.model_btns.items():
            btn.set_variant("tonal" if name == cur else "ghost")

    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        for b in self._buttons:
            b.set_enabled(not busy)
        if busy:
            self._show_progress(True)
            self.progress.set(0)
        else:
            self.start_btn.set_enabled(True)

    def _show_progress(self, show: bool) -> None:
        """进度条按需出现/收起，收起时把状态文字的间距补回来。"""
        if show and not self.progress.winfo_ismapped():
            self.progress.pack(fill=tk.X, pady=(theme.S4, theme.S2),
                               before=self.status_label)
            self.status_label.pack_configure(pady=(0, 0))
        elif not show and self.progress.winfo_ismapped():
            self.progress.pack_forget()
            self.status_label.pack_configure(pady=(theme.S4, 0))

    def _restore_status(self) -> None:
        """恢复状态行（完成后它被结果面板顶替掉了）。"""
        if self.status_label.winfo_ismapped():
            return
        pad = (0, 0) if self.progress.winfo_ismapped() else (theme.S4, 0)
        self.status_label.pack(fill=tk.X, pady=pad)

    # ------------------------------------------------------------- 模型预热
    def _warmup(self) -> None:
        """启动后后台预加载模型，转换时不再等 30~60 秒。"""

        def work() -> None:
            try:
                with self._model_lock:
                    engine.get_session(self.model_var.get())
                self._model_ready = True
                if not self.busy:
                    self.events.put(("status", "模型已就绪，随时可开始转换"))
            except Exception as exc:  # noqa: BLE001
                engine.log(f"[预热] 模型加载失败（转换时会重试）：{exc}")

        threading.Thread(target=work, daemon=True).start()

    def _set_model(self, name: str, label: str) -> None:
        if self.busy:
            return
        self.model_var.set(name)
        self._model_ready = False  # 切换后需要重新预热
        self.status_label.configure(text=label, fg=COL_SUB)
        self._sync_model_buttons()
        self._warmup()

    # --------------------------------------------------------------- 文件
    def add_files(self) -> None:
        if self.busy:
            return
        paths = filedialog.askopenfilenames(
            title="选择图片（可多选）",
            filetypes=[("图片文件", "*.jpg *.jpeg *.png *.webp *.bmp *.tif *.tiff"),
                       ("所有文件", "*.*")])
        if paths:
            self.add_paths([Path(p) for p in paths])

    def add_folder(self) -> None:
        if self.busy:
            return
        d = filedialog.askdirectory(title="选择包含图片的文件夹")
        if d:
            self.add_paths([Path(d)])

    def add_paths(self, paths) -> None:
        added = 0
        for p in paths:
            try:
                p = Path(p)
            except Exception:  # noqa: BLE001
                continue
            if not p.exists():
                continue
            if p.is_dir():
                for f in sorted(p.rglob("*")):
                    if f.is_file() and f.suffix.lower() in engine.IMAGE_EXTS:
                        if self._add_one(f):
                            added += 1
            elif p.suffix.lower() in engine.IMAGE_EXTS:
                if self._add_one(p):
                    added += 1
        if added:
            self.count_label.configure(text=f"已选 {len(self.files)} 张图片")
            self.status_label.configure(
                text=f"已加入 {added} 张（共 {len(self.files)} 张），点击「开始转换」",
                fg=theme.INK_MUTE)
            self.refresh_preview()

    def _add_one(self, f: Path) -> bool:
        r = f.resolve()
        if r in self._seen:
            return False
        self._seen.add(r)
        self.files.append(f)
        return True

    def remove_file(self, index: int) -> None:
        if self.busy or not (0 <= index < len(self.files)):
            return
        self._seen.discard(self.files[index].resolve())
        self.files.pop(index)
        self.count_label.configure(text=f"已选 {len(self.files)} 张图片")
        self.refresh_preview()

    def clear_all(self) -> None:
        if self.busy:
            return
        self.files.clear()
        self._seen.clear()
        self.count_label.configure(text="已选 0 张图片")
        self.status_label.configure(text="请先添加要转换的图片", fg=theme.INK_MUTE)
        self.done_frame.pack_forget()
        self._show_progress(False)
        self.progress.set(0)
        self._restore_status()
        self.refresh_preview()

    def choose_output(self) -> None:
        if self.busy:
            return
        d = filedialog.askdirectory(title="选择输出文件夹", initialdir=str(self.out_dir))
        if d:
            self.out_dir = Path(d)
            self.out_label.configure(text=self._short_path(self.out_dir))

    def open_output(self) -> None:
        """打开输出文件夹：三保险并给出可见反馈，绝不静默失败。"""
        try:
            self.out_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:  # noqa: BLE001
            engine.log(f"[错误] 创建输出文件夹失败：{exc}")
            if not SMOKE:
                messagebox.showerror(APP_TITLE, f"创建输出文件夹失败：\n{exc}")
            return
        path = str(self.out_dir)
        errors: list[str] = []
        import subprocess
        for name, fn in (
            ("os.startfile", lambda: os.startfile(path)),
            ("explorer.exe", lambda: subprocess.Popen(["explorer.exe", path])),
            ("cmd start", lambda: subprocess.Popen(["cmd.exe", "/c", "start", "", path])),
        ):
            try:
                fn()
                engine.log(f"[信息] 已通过 {name} 打开输出文件夹：{path}")
                return
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{name}：{exc}")
                engine.log(f"[警告] {name} 失败：{exc}")
        if not SMOKE:
            messagebox.showwarning(
                APP_TITLE,
                f"自动打开文件夹失败（{len(errors)} 种方式均被系统拦截）。\n"
                f"输出文件夹路径：\n{path}\n\n"
                f"请手动复制该路径到文件资源管理器地址栏打开，或告知技术人员"
                f"（详情已记入「启动日志.txt」）。")

    # ------------------------------------------------------------- 拖拽
    def _on_drop(self, event) -> str:
        try:
            items = self.root.tk.splitlist(event.data)
        except Exception:  # noqa: BLE001
            items = [event.data]
        engine.log(f"[拖拽] 收到 {len(items)} 个路径")
        self.add_paths([Path(i) for i in items])
        return "copy"

    # ------------------------------------------------------------- 转换
    def start_convert(self) -> None:
        if self.busy or not self.files:
            return
        self.finished = False
        self.done_frame.pack_forget()
        self._restore_status()
        self._set_busy(True)
        self._convert_start = time.time()
        self.status_label.configure(text="正在准备…")
        threading.Thread(target=self._worker, daemon=True).start()

    def _build_args(self):
        parser = engine.build_parser()
        a = parser.parse_args([])
        a.model = self.model_var.get()
        if a.square is None:
            a.square = True
        if a.size is None:
            a.size = 1200
        if a.format is None:
            a.format = "jpg"
        a.transparent = False
        a.quality = 95
        return a

    def _worker(self) -> None:
        args = self._build_args()
        out = self.out_dir
        files = list(self.files)
        total = len(files)
        ok = fail = 0
        failures: list[str] = []
        start = time.monotonic()
        try:
            self.events.put(("loading", args.model))
            with self._model_lock:
                engine.get_session(args.model)
            self.events.put(("ready",))
            for i, f in enumerate(files, 1):
                try:
                    dst = out / (f.stem + ".jpg")
                    engine.process_one(f, dst, args)
                    ok += 1
                except Exception as exc:  # noqa: BLE001
                    fail += 1
                    failures.append(f"{f.name}：{type(exc).__name__}: {exc}")
                self.events.put(("progress", i, total, time.monotonic() - start,
                                 f.name, ok, fail))
            self.events.put(("done", ok, fail, failures, out))
        except Exception as exc:  # noqa: BLE001
            self.events.put(("fatal", f"{type(exc).__name__}: {exc}"))

    def _on_close(self) -> None:
        if self.busy:
            if not messagebox.askyesno(APP_TITLE, "正在转换中，确定要退出吗？"):
                return
        self.root.destroy()

    # ------------------------------------------------------------- 事件泵
    def _poll(self) -> None:
        try:
            # 缩略图异步送达（每轮最多贴 6 张，保持界面流畅）
            for _ in range(6):
                gen, idx, im = self._thumb_queue.get_nowait()
                if gen != self._preview_gen:
                    continue
                children = self._grid.winfo_children()
                if 0 <= idx < len(children):
                    card = children[idx]
                    holder = getattr(card, "_holder", None)
                    if holder is not None:
                        ph = _thumb_to_photo(im)  # 主线程内转换，Tk 安全
                        if ph is not None:
                            self.thumbs[str(getattr(card, "_f"))] = ph
                            holder.configure(image=ph, text="")
                        else:
                            holder.configure(text="无法预览", fg=COL_SUB)
        except queue.Empty:
            pass
        # 进度条动画：加载中整条来回扫；转换中轻微呼吸，肉眼可见“在工作”
        if self._animating:
            t = time.time()
            if self._loading:
                self.progress.set(abs(math.sin(t * 1.6)))
            else:
                self.progress.set(min(1.0, self._base_frac + 0.015 * math.sin(t * 6)))
        try:
            while True:
                ev = self.events.get_nowait()
                kind = ev[0]
                if kind == "status":
                    self.status_label.configure(text=ev[1], fg=COL_SUB)
                elif kind == "loading":
                    self._loading, self._animating = True, True
                    self.status_label.configure(text="正在加载模型（首次约 30~60 秒，请稍候）…",
                                                fg=COL_SUB)
                elif kind == "ready":
                    self._loading, self._animating = False, False
                    self.status_label.configure(text="模型就绪，开始转换…", fg=COL_TEXT)
                elif kind == "progress":
                    _, i, total, elapsed, name, ok, fail = ev
                    self._base_frac = i / total
                    self.progress.set(i / total)
                    remain = elapsed / i * (total - i)
                    self.status_label.configure(
                        text=f"处理中 {i}/{total}：{name}"
                             f"（已用 {_fmt_sec(elapsed)}，预计还需 {_fmt_sec(remain)}）",
                        fg=COL_TEXT)
                elif kind == "done":
                    _, ok, fail, failures, out = ev
                    self._animating = False
                    self._finish(ok, fail, failures, out)
                elif kind == "fatal":
                    self.status_label.configure(text="出错了：" + ev[1], fg=COL_DANGER)
                    if not SMOKE:
                        messagebox.showerror(APP_TITLE, "转换出错：\n" + ev[1] + "\n\n详细见「启动日志.txt」")
                    self._set_busy(False)
                    self._animating = False
                    self.finished = True
        except queue.Empty:
            pass
        except Exception as exc:  # noqa: BLE001
            engine.log(f"[GUI] 轮询异常：{exc}")
        if not self.finished:
            self.root.after(100, self._poll)
        elif SMOKE:
            self.root.after(200, self.root.destroy)

    def _finish(self, ok: int, fail: int, failures: list, out: Path) -> None:
        self._set_busy(False)
        self.finished = True
        self.smoke_ok = ok
        self.smoke_fail = fail
        self.smoke_rc = 0 if fail == 0 else 1
        dur = time.time() - self._convert_start
        if fail == 0:
            self.done_msg.configure(
                text=f"✓ 任务完成！成功 {ok} 张 · 耗时 {dur:.0f} 秒\n白底图已放在：{out}", fg=COL_OK)
        else:
            self.done_msg.configure(
                text=f"任务完成（{ok} 成功 / {fail} 失败）\n白底图已放在：{out}",
                fg=theme.WARNING)
            self.fail_msg.configure(text="失败明细：\n" + "\n".join(failures[:8]))
        # 结果面板接管状态区：进度行与状态行让位，避免同一件事说两遍
        self._show_progress(False)
        self.status_label.pack_forget()
        self.done_frame.pack(fill=tk.X)
        engine.log(f"[完成] 成功 {ok} 张，失败 {fail} 张，输出 {out}")

    # ------------------------------------------------------------- 刷新预览
    def refresh_preview(self) -> None:
        """先放占位卡立即响应，缩略图由后台线程逐张生成（拖入大图不卡界面）。"""
        self._preview_gen += 1
        for w in self._grid.winfo_children():
            w.destroy()
        self.thumbs.clear()
        if not self.files:
            self._show_hint()
            return
        self.hint.place_forget()
        for i, f in enumerate(self.files):
            card = tk.Frame(self._grid, bg=COL_CARD)
            card.grid(row=i // self._cols, column=i % self._cols,
                      padx=6, pady=6, sticky="n")
            holder_box = tk.Frame(card, width=THUMB, height=THUMB, bg=COL_TRACK)
            holder_box.pack()
            holder_box.pack_propagate(False)
            holder = tk.Label(holder_box, bg=COL_TRACK)
            holder.pack(fill=tk.BOTH, expand=True)
            card._holder = holder
            card._f = f
            name_row = tk.Frame(card, bg=COL_CARD)
            name_row.pack(fill=tk.X, pady=(theme.S1, 0))
            short = f.name if len(f.name) <= 11 else f.name[:9] + "…"
            tk.Label(name_row, text=short, bg=COL_CARD, fg=COL_SUB,
                     font=F(theme.F_LABEL), anchor="w").pack(side=tk.LEFT)
            # 默认灰色（一排红叉太吵），悬停才变红并给浅红底，指向明确
            btn = tk.Label(name_row, text="✕", bg=COL_CARD, fg=theme.INK_MUTE,
                           cursor="hand2", font=F(theme.F_LABEL, True))
            btn.pack(side=tk.RIGHT, padx=(theme.S1, 0))
            btn.bind("<Button-1>", lambda e, idx=i: self.remove_file(idx))
            btn.bind("<Enter>", lambda e: e.widget.configure(
                fg=theme.DANGER, bg=theme.DANGER_SOFT))
            btn.bind("<Leave>", lambda e: e.widget.configure(
                fg=theme.INK_MUTE, bg=COL_CARD))

        # 末尾补一格「继续添加」：填满最后一行，同时把"还能继续加图"说清楚
        idx = len(self.files)
        addtile = tk.Frame(self._grid, bg=COL_CARD)
        addtile.grid(row=idx // self._cols, column=idx % self._cols,
                     padx=6, pady=6, sticky="n")
        box = tk.Frame(addtile, width=THUMB, height=THUMB, bg=theme.SURFACE_ALT,
                       cursor="hand2", highlightthickness=1,
                       highlightbackground=theme.BORDER)
        box.pack()
        box.pack_propagate(False)
        plus = tk.Label(box, text="＋", bg=theme.SURFACE_ALT, fg=theme.INK_MUTE,
                        font=F(theme.F_TITLE), cursor="hand2")
        plus.place(relx=0.5, rely=0.5, anchor="center")
        for widget in (box, plus):
            widget.bind("<Button-1>", lambda e: self.add_files())
            widget.bind("<Enter>", lambda e: (
                box.configure(bg=theme.BRAND_SOFT), plus.configure(bg=theme.BRAND_SOFT)))
            widget.bind("<Leave>", lambda e: (
                box.configure(bg=theme.SURFACE_ALT), plus.configure(bg=theme.SURFACE_ALT)))
        tk.Label(addtile, text="继续添加", bg=COL_CARD, fg=theme.INK_MUTE,
                 font=F(theme.F_LABEL)).pack(pady=(theme.S1, 0))

        gen = self._preview_gen
        files = list(self.files)

        def work() -> None:
            for idx, f in enumerate(files):
                try:
                    im = load_thumb(f)
                except Exception:  # noqa: BLE001
                    im = None
                self._thumb_queue.put((gen, idx, im))

        threading.Thread(target=work, daemon=True).start()


def _silence_missing_streams() -> None:
    """windowed（无控制台）模式下 stdout/stderr 为 None，重定向到 NUL。

    真正的运行记录在「启动日志.txt」（engine.log 在冻结版会自动写）。
    """
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")


def main() -> int:
    _silence_missing_streams()
    engine.init_runtime()
    engine.log(f"[GUI] 启动 {APP_TITLE}（拖拽支持：{'开' if HAVE_DND else '关'}）")
    root = (TkinterDnD.Tk() if HAVE_DND else tk.Tk())  # type: ignore
    root.tk.call("tk", "scaling", 1.25)
    app = WhiteBgApp(root)

    if SMOKE:
        def smoke_start() -> None:
            engine.log("[SMOKE] 自动添加 input 文件夹并开始转换（GUI_SMOKE 模式）")
            inp = engine.base_dir() / "input"
            if not inp.exists():
                inp = engine.base_dir().parent / "input"
            app.add_paths([inp])
            if app.files:
                app.start_convert()
            else:
                engine.log(f"[SMOKE] input 为空（{inp}），直接结束")
                root.destroy()

        def smoke_watch() -> None:
            if app.finished:
                engine.log(f"[SMOKE] 结束：success={getattr(app, 'smoke_ok', None)}")
                root.destroy()
            elif time.time() - app._convert_start > 2400 and app.busy:
                engine.log("[SMOKE] 超时退出")
                root.destroy()
            else:
                root.after(1000, smoke_watch)

        root.after(800, smoke_start)
        root.after(1500, smoke_watch)

    root.mainloop()
    engine.log("[GUI] 正常退出")
    return getattr(app, "smoke_rc", 0)


def launch() -> None:
    """图形界面入口：兜底异常、弹窗提示，并强制结束进程（避免 Tk 残留线程卡住退出）。"""
    code = 0
    try:
        code = main()
    except Exception as exc:  # noqa: BLE001
        engine.log("\n!! 程序运行出错：\n"
                   + "".join(_tb.format_exception(type(exc), exc, exc.__traceback__)))
        if not SMOKE:
            try:
                import ctypes

                ctypes.windll.user32.MessageBoxW(
                    None,
                    f"白底图转换工具运行出错：\n\n{exc}\n\n完整信息见「启动日志.txt」",
                    APP_TITLE + " - 错误",
                    0x10,
                )
            except Exception:  # noqa: BLE001
                pass
        code = 4
    finally:
        os._exit(code)
