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

from . import engine

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD  # type: ignore
    HAVE_DND = True
except Exception:  # noqa: BLE001
    HAVE_DND = False

from PIL import Image, ImageDraw, ImageTk

APP_TITLE = "白底图转换工具"
THUMB = 104
COLS = 6
# 默认“速度优先”模型（约 2 秒/张），可一键切“质量优先”
MODELS = ["u2net", "birefnet-general-lite", "birefnet-general"]
SPEED_MODEL = "u2net"
QUALITY_MODEL = "birefnet-general-lite"
SMOKE = os.environ.get("GUI_SMOKE") == "1"

# ---------------------------------------------------------------------------
# iOS 风格调色板（原生渲染，无需联网素材）
# ---------------------------------------------------------------------------
COL_BG = "#F2F2F7"
COL_CARD = "#FFFFFF"
COL_TEXT = "#1C1C1E"
COL_SUB = "#8E8E93"
COL_ACCENT = "#007AFF"
COL_ACCENT_DARK = "#0063D6"
COL_HOVER = "#EDF3FF"
COL_TRACK = "#E9E9EB"
COL_DANGER = "#FF3B30"
COL_OK = "#34C759"
COL_HINT = "#B0B0B8"
RADIUS = 16
CARD_PAD = 16
WIN_W = 980
WIN_H = 760
BTN_W = WIN_W - 2 * 24 - 2 * CARD_PAD  # 卡片内主按钮宽度


def F(size: int, bold: bool = False):
    return ("Segoe UI", size, "bold" if bold else "normal")


def round_rect_pts(x1, y1, x2, y2, r):
    return [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
            x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]


class RoundedFrame(tk.Canvas):
    """白色圆角卡片，内容放 inner 子框架里。"""

    def __init__(self, master, radius=RADIUS, bg=COL_CARD, pad=CARD_PAD, **kw):
        super().__init__(master, bg=COL_BG, highlightthickness=0, bd=0, **kw)
        self._radius, self._fill, self._pad = radius, bg, pad
        self.inner = tk.Frame(self, bg=bg)
        self._win = self.create_window(pad, pad, anchor="nw", window=self.inner)
        self.bind("<Configure>", self._redraw)

    def _redraw(self, _e=None):
        w, h = self.winfo_width(), self.winfo_height()
        if w < 20 or h < 20:
            return
        self.delete("card")
        try:
            # 个别显卡/Tk 版本对 smooth 多边形渲染异常，兜底用普通矩形
            self.create_polygon(round_rect_pts(2, 2, w - 2, h - 2, self._radius),
                                smooth=True, fill=self._fill, outline="", tags="card")
        except tk.TclError:
            self.create_rectangle(2, 2, w - 2, h - 2, fill=self._fill,
                                  outline="", tags="card")
        self.coords(self._win, self._pad, self._pad)
        try:
            self.itemconfigure(self._win, width=w - 2 * self._pad)
        except tk.TclError:
            pass


class iOSButton(tk.Frame):
    """原生 tk.Button 封装（固定像素尺寸 + 扁平配色）。
    改用系统原生控件渲染：任何机器上都不会出现黑块/颜色缺失，
    悬停、按下、禁用等交互全部由系统保证。"""

    def __init__(self, master, text, command=None, accent=True, width=120, height=40,
                 font_size=11, bold=False, bg=None, fg=None):
        super().__init__(master, width=width, height=height, bg=COL_BG)
        self.pack_propagate(False)
        self._accent = accent
        self._fg = fg or ("#FFFFFF" if accent else COL_TEXT)
        self._bg = bg or (COL_ACCENT if accent else COL_CARD)
        self._bg_hover = "#CFE4FF" if bg else (COL_ACCENT_DARK if accent else COL_HOVER)
        self._bg_disabled = COL_TRACK
        border = "#B8C4D6" if accent else "#D1D1D6"
        self.btn = tk.Button(
            self, text=text, command=command, font=F(font_size, bold),
            bg=self._bg, fg=self._fg,
            activebackground=self._bg_hover, activeforeground=self._fg,
            relief="flat", bd=0, cursor="hand2", padx=8, pady=4,
            highlightthickness=1, highlightbackground=border, highlightcolor=COL_ACCENT)
        self.btn.pack(fill=tk.BOTH, expand=True)

    def set_enabled(self, enabled: bool):
        self.btn.configure(state="normal" if enabled else "disabled",
                           bg=self._bg if enabled else self._bg_disabled,
                           fg=self._fg if enabled else COL_SUB)


class RoundedProgress(tk.Canvas):
    """胶囊进度条。"""

    def __init__(self, master, width=330, height=10, radius=5):
        super().__init__(master, width=width, height=height + 4, bg=COL_CARD,
                         highlightthickness=0, bd=0)
        self._pw, self._ph, self._pr = width, height + 4, radius
        self._frac = 0.0
        self._draw()

    def _draw(self):
        self.delete("all")
        try:
            self.create_polygon(round_rect_pts(2, 2, self._pw - 2, self._ph - 2, self._pr),
                                smooth=True, fill=COL_TRACK)
            fw = (self._pw - 6) * self._frac
            if fw >= self._pr * 2:
                self.create_polygon(round_rect_pts(3, 3, 3 + fw, self._ph - 3, self._pr),
                                    smooth=True, fill=COL_ACCENT)
            elif fw > 2:
                self.create_polygon(round_rect_pts(3, 3, 3 + fw, self._ph - 3, fw / 2),
                                    smooth=True, fill=COL_ACCENT)
        except tk.TclError:  # 渲染兼容性兜底
            fw = (self._pw - 6) * self._frac
            self.create_rectangle(2, 2, self._pw - 2, self._ph - 2, fill=COL_TRACK)
            if fw > 2:
                self.create_rectangle(3, 3, 3 + fw, self._ph - 3, fill=COL_ACCENT)

    def set(self, frac: float):
        self._frac = max(0.0, min(1.0, frac))
        self._draw()


def load_thumb(path: Path, size: int = THUMB, radius: int = 14) -> Image.Image:
    """后台线程用：只做纯 PIL 处理（不碰 Tk），返回圆角 RGBA 图。"""
    im = Image.open(path).convert("RGBA")
    im.thumbnail((size, size), Image.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.paste(im, ((size - im.width) // 2, (size - im.height) // 2), im)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    canvas.putalpha(mask)
    return canvas


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

    def _btn(self, parent, text, command, accent=True, width=120, height=40,
             font_size=11, bold=False, bg=None, fg=None):
        b = iOSButton(parent, text, command=command, accent=accent, width=width,
                      height=height, font_size=font_size, bold=bold, bg=bg, fg=fg)
        self._buttons.append(b)
        return b

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        self.root.configure(bg=COL_BG)
        self.root.title(APP_TITLE)
        self.root.geometry(f"{WIN_W}x{WIN_H}")
        self.root.minsize(900, 640)
        if not SMOKE:
            self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        outer = tk.Frame(self.root, bg=COL_BG)
        outer.pack(fill=tk.BOTH, expand=True, padx=24, pady=(18, 20))

        # 头部
        head = tk.Frame(outer, bg=COL_BG)
        head.pack(fill=tk.X, pady=(0, 14))
        tk.Label(head, text="白底图转换", bg=COL_BG, fg=COL_TEXT,
                 font=F(24, True)).pack(anchor="w")
        tk.Label(head, text="批量抠图 · 白底电商主图 · 全本地运行",
                 bg=COL_BG, fg=COL_SUB, font=F(11)).pack(anchor="w", pady=(2, 0))

        # 卡片1：素材操作
        card1 = RoundedFrame(outer)
        card1.pack(fill=tk.X)
        c1 = card1.inner
        row1 = tk.Frame(c1, bg=COL_CARD)
        row1.pack(fill=tk.X)
        self._btn(row1, "＋ 添加图片", self.add_files, accent=False, width=120).pack(side=tk.LEFT)
        self._btn(row1, "添加文件夹", self.add_folder, accent=False, width=120).pack(side=tk.LEFT, padx=(10, 0))
        self._btn(row1, "清空", self.clear_all, accent=False, width=72).pack(side=tk.LEFT, padx=(10, 0))
        # 常驻「打开输出文件夹」按钮：浅蓝底蓝字，与白色按钮明显区分
        self._btn(row1, "打开输出文件夹", self.open_output, accent=False, width=150,
                  height=34, font_size=10, bg=COL_HOVER, fg=COL_ACCENT,
                  ).pack(side=tk.RIGHT, padx=(0, 12))
        self.count_label = tk.Label(row1, text="已选 0 张图片", bg=COL_CARD, fg=COL_SUB, font=F(11))
        self.count_label.pack(side=tk.RIGHT)

        row2 = tk.Frame(c1, bg=COL_CARD)
        row2.pack(fill=tk.X, pady=(14, 0))
        tk.Label(row2, text="输出位置", bg=COL_CARD, fg=COL_SUB, font=F(10)).pack(side=tk.LEFT)
        self.out_label = tk.Label(row2, text=str(self.out_dir), bg=COL_CARD,
                                  fg=COL_TEXT, font=F(11))
        self.out_label.pack(side=tk.LEFT, padx=(8, 0))
        self._btn(row2, "更改…", self.choose_output, accent=False, width=76,
                  height=30, font_size=10).pack(side=tk.LEFT, padx=(8, 0))
        tk.Label(row2, text="模型", bg=COL_CARD, fg=COL_SUB, font=F(10)).pack(side=tk.RIGHT, padx=(6, 0))
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("IOS.TCombobox", fieldbackground=COL_CARD, background=COL_CARD,
                        foreground=COL_TEXT, arrowcolor=COL_ACCENT, bordercolor=COL_TRACK,
                        lightcolor=COL_TRACK, darkcolor=COL_TRACK, padding=4)
        ttk.Combobox(row2, textvariable=self.model_var, values=MODELS, state="readonly",
                     width=22, style="IOS.TCombobox", font=F(10)).pack(side=tk.RIGHT)
        self._btn(row2, "速度优先", lambda: self._set_model(SPEED_MODEL, "速度优先（u2net，约 2 秒/张）"),
                  accent=False, width=88, height=30, font_size=10).pack(side=tk.RIGHT, padx=(0, 12))
        self._btn(row2, "质量优先", lambda: self._set_model(QUALITY_MODEL, "质量优先（birefnet-lite，约 10 秒/张）"),
                  accent=False, width=100, height=30, font_size=10).pack(side=tk.RIGHT, padx=(0, 12))

        # 卡片2：预览
        card2 = RoundedFrame(outer)
        card2.pack(fill=tk.BOTH, expand=True, pady=(14, 0))
        c2 = card2.inner
        self.canvas = tk.Canvas(c2, bg=COL_CARD, highlightthickness=0, bd=0)
        vsb = ttk.Scrollbar(c2, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._grid = tk.Frame(self.canvas, bg=COL_CARD)
        gwin = self.canvas.create_window((4, 4), anchor="nw", window=self._grid)
        self._grid.bind("<Configure>",
                        lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>",
                         lambda e: self.canvas.itemconfigure(gwin, width=e.width - 8))
        self.canvas.bind_all("<MouseWheel>",
                             lambda e: self.canvas.yview_scroll(int(-e.delta / 120), "units"))
        self.hint = tk.Label(c2, text="把图片或文件夹拖到此处，或点击「＋ 添加图片」\n"
                                      "支持 jpg / png / webp / bmp / tif 等格式",
                             bg=COL_CARD, fg=COL_HINT, font=F(14), justify=tk.CENTER)
        self.hint.place(relx=0.5, rely=0.45, anchor=tk.CENTER)

        # 卡片3：底部
        card3 = RoundedFrame(outer)
        card3.pack(fill=tk.X, pady=(14, 0))
        c3 = card3.inner
        self.start_btn = self._btn(c3, "开始转换", self.start_convert, accent=True,
                                   width=BTN_W, height=46, font_size=14, bold=True)
        self.start_btn.pack(fill=tk.X)

        prow = tk.Frame(c3, bg=COL_CARD)
        prow.pack(fill=tk.X, pady=(14, 0))
        self.progress = RoundedProgress(prow, width=330)
        self.progress.pack(side=tk.LEFT)
        self.status_label = tk.Label(prow, text="请先添加要转换的图片", bg=COL_CARD,
                                     fg=COL_SUB, font=F(10))
        self.status_label.pack(side=tk.LEFT, padx=(14, 0))

        # 完成面板
        self.done_frame = tk.Frame(c3, bg=COL_CARD)
        self.done_row = tk.Frame(self.done_frame, bg=COL_CARD)
        self.done_row.pack(fill=tk.X, pady=(14, 0))
        self.done_msg = tk.Label(self.done_row, text="", bg=COL_CARD, fg=COL_OK,
                                 font=F(12, True), justify=tk.LEFT, wraplength=660)
        self.done_msg.pack(side=tk.LEFT)
        self.open_btn = self._btn(self.done_row, "打开输出文件夹", self.open_output,
                                  accent=False, width=170, height=36, font_size=11)
        self.open_btn.pack(side=tk.LEFT, padx=(16, 0))
        self.fail_msg = tk.Label(self.done_frame, text="", bg=COL_CARD, fg=COL_DANGER,
                                 font=F(10), justify=tk.LEFT, wraplength=870)
        self.fail_msg.pack(anchor="w", pady=(8, 0))
        # 拖拽目标覆盖：根窗口 + 预览区及其子件
        self._drop_widgets = [self.root, outer, c2, self.canvas, self._grid, self.hint]

    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        for b in self._buttons:
            b.set_enabled(not busy)
        if busy:
            self.progress.set(0)
        else:
            self.start_btn.set_enabled(True)

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
                text=f"已加入 {added} 张（共 {len(self.files)} 张），点击「开始转换」")
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
        self.status_label.configure(text="请先添加要转换的图片")
        self.done_frame.pack_forget()
        self.refresh_preview()

    def choose_output(self) -> None:
        if self.busy:
            return
        d = filedialog.askdirectory(title="选择输出文件夹", initialdir=str(self.out_dir))
        if d:
            self.out_dir = Path(d)
            self.out_label.configure(text=str(self.out_dir))

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
                            holder.configure(image=ph, text="", width=0, height=0)
                        else:
                            holder.configure(text="无法预览", width=13, height=5)
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
                text=f"任务完成（{ok} 成功 / {fail} 失败）\n白底图已放在：{out}", fg="#B26A00")
            self.fail_msg.configure(text="失败明细：\n" + "\n".join(failures[:8]))
        self.status_label.configure(
            text=f"已完成：成功 {ok} 张，失败 {fail} 张（{dur:.0f} 秒）", fg=COL_TEXT)
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
            return
        self.hint.place_forget()
        for i, f in enumerate(self.files):
            card = tk.Frame(self._grid, bg=COL_CARD)
            card.grid(row=i // COLS, column=i % COLS, padx=7, pady=7, sticky="n")
            holder = tk.Label(card, text="…", width=13, height=5, bg=COL_TRACK, fg=COL_SUB)
            holder.pack()
            card._holder = holder
            card._f = f
            name = f.name
            tk.Label(card, text=name if len(name) <= 13 else name[:10] + "…",
                     bg=COL_CARD, fg=COL_TEXT, font=F(9), width=14).pack(pady=(4, 0))
            btn = tk.Label(card, text="✕", bg=COL_CARD, fg=COL_DANGER, cursor="hand2",
                           font=F(11, True))
            btn.pack(pady=(2, 0))
            btn.bind("<Button-1>", lambda e, idx=i: self.remove_file(idx))
            btn.bind("<Enter>", lambda e: e.widget.configure(fg="#D00000"))
            btn.bind("<Leave>", lambda e: e.widget.configure(fg=COL_DANGER))
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
