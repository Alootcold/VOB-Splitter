"""VOB Splitter 图形界面（Tkinter，Python 标准库，零第三方依赖）。

与 Flutter 版同构：左侧控制栏（源 / 切分方式 / 输出），右侧章节表格 + 日志，
顶栏显示状态与「无损校验」结论。切分在后台线程里跑，界面不卡。

    python -m vobsplit.gui
"""

from __future__ import annotations

import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, ttk
from typing import List, Optional

from .chapters import Chapter, ChapterSpec, parse_time_list
from .runner import Handlers, RunResult, run_split

# ---- 色板（与 DESIGN.md 一致）----
SURFACE = "#0D0E11"
SURFACE_LOWEST = "#111318"
SURFACE_CONTAINER = "#16181D"
SURFACE_HIGH = "#1C1F26"
OUTLINE = "#2A2E37"
OUTLINE_VARIANT = "#3A3F4A"
ON_SURFACE = "#E7E9ED"
ON_SURFACE_VARIANT = "#9BA1AC"
PRIMARY = "#5AA9B8"
ON_PRIMARY = "#06171B"
ERROR = "#E06C75"

MONO = ("Consolas", 10)


def _fmt_time(seconds: Optional[float]) -> str:
    if seconds is None:
        return "—"
    seconds = max(0.0, seconds)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return "%d:%02d:%06.3f" % (h, m, s)


def _fmt_size(n: int) -> str:
    if n >= 1048576:
        return "%.1f MB" % (n / 1048576.0)
    return "%.1f KB" % (n / 1024.0)


class VobSplitterApp(tk.Tk):
    """主窗口。"""

    def __init__(self) -> None:
        super().__init__()
        self.title("VOB Splitter — DVD VOB 无损分割")
        # 窗口尺寸按屏幕自适应，别让默认高度超出屏幕（会被切掉）
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        width = min(1240, max(940, screen_w - 80))
        height = min(800, max(600, screen_h - 90))
        self.geometry("%dx%d" % (width, height))
        self.minsize(min(940, width - 40), min(600, height - 40))
        self.configure(bg=SURFACE)
        self._set_window_icon()

        self._queue: "queue.Queue" = queue.Queue()
        self._running = False
        self._verdict: Optional[bool] = None

        self._init_style()
        self._build_ui()
        self.after(80, self._poll)

    # ---------------------------------------------------------------- 样式
    def _set_window_icon(self) -> None:
        """设置窗口图标（打包后资源在 _MEIPASS 下）。"""
        base = getattr(sys, "_MEIPASS",
                       os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        ico = os.path.join(base, "assets", "vobsplit.ico")
        png = os.path.join(base, "assets", "vobsplit.png")
        try:
            if os.path.isfile(ico):
                self.iconbitmap(default=ico)
                return
        except Exception:
            pass
        try:
            if os.path.isfile(png):
                self._icon_img = tk.PhotoImage(file=png)   # 保留引用，否则会被回收
                self.iconphoto(True, self._icon_img)
        except Exception:
            pass

    def _init_style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")

        style.configure("TFrame", background=SURFACE)
        style.configure("Side.TFrame", background=SURFACE_LOWEST)
        style.configure("Card.TFrame", background=SURFACE_CONTAINER)
        style.configure("Head.TFrame", background=SURFACE_HIGH)

        style.configure("TLabel", background=SURFACE, foreground=ON_SURFACE)
        style.configure("Side.TLabel", background=SURFACE_LOWEST, foreground=ON_SURFACE)
        style.configure("Muted.TLabel", background=SURFACE, foreground=ON_SURFACE_VARIANT,
                        font=("Segoe UI", 9))
        style.configure("MutedCard.TLabel", background=SURFACE_CONTAINER,
                        foreground=ON_SURFACE_VARIANT, font=("Segoe UI", 9))
        style.configure("MutedSide.TLabel", background=SURFACE_LOWEST,
                        foreground=ON_SURFACE_VARIANT, font=("Segoe UI", 9))
        style.configure("Section.TLabel", background=SURFACE_LOWEST, foreground=ON_SURFACE_VARIANT,
                        font=("Segoe UI", 8, "bold"))
        style.configure("Title.TLabel", background=SURFACE_LOWEST, foreground=ON_SURFACE,
                        font=("Segoe UI", 12, "bold"))
        style.configure("Badge.TLabel", background=SURFACE_HIGH, foreground=PRIMARY,
                        font=("Segoe UI", 9, "bold"))
        style.configure("BadgeFail.TLabel", background=SURFACE_HIGH, foreground=ERROR,
                        font=("Segoe UI", 9, "bold"))
        style.configure("BadgeIdle.TLabel", background=SURFACE_HIGH, foreground=OUTLINE_VARIANT,
                        font=("Segoe UI", 9, "bold"))

        style.configure("TEntry", fieldbackground=SURFACE_LOWEST, foreground=ON_SURFACE,
                        insertcolor=ON_SURFACE, bordercolor=OUTLINE, lightcolor=OUTLINE,
                        darkcolor=OUTLINE, padding=6)
        style.map("TEntry", bordercolor=[("focus", PRIMARY)],
                  lightcolor=[("focus", PRIMARY)], darkcolor=[("focus", PRIMARY)])

        style.configure("TButton", background=SURFACE_CONTAINER, foreground=ON_SURFACE,
                        bordercolor=OUTLINE, padding=(10, 6), font=("Segoe UI", 9))
        style.map("TButton", background=[("active", SURFACE_HIGH)],
                  bordercolor=[("active", OUTLINE_VARIANT)])
        style.configure("Accent.TButton", background=PRIMARY, foreground=ON_PRIMARY,
                        bordercolor=PRIMARY, padding=(10, 8), font=("Segoe UI", 10, "bold"))
        style.map("Accent.TButton", background=[("active", PRIMARY)],
                  foreground=[("disabled", OUTLINE_VARIANT)])
        style.configure("Link.TButton", background=SURFACE_LOWEST, foreground=ON_SURFACE_VARIANT,
                        bordercolor=OUTLINE, padding=(6, 3), font=("Segoe UI", 8))

        style.configure("TRadiobutton", background=SURFACE_LOWEST, foreground=ON_SURFACE,
                        font=("Segoe UI", 9), focuscolor=SURFACE_LOWEST)
        style.map("TRadiobutton", background=[("active", SURFACE_LOWEST)])
        style.configure("TCheckbutton", background=SURFACE_LOWEST, foreground=ON_SURFACE_VARIANT,
                        font=("Segoe UI", 9), focuscolor=SURFACE_LOWEST,
                        indicatorcolor=ON_SURFACE_VARIANT, indicatorbackground=SURFACE_LOWEST)
        style.map("TCheckbutton", background=[("active", SURFACE_LOWEST)],
                  indicatorcolor=[("selected", PRIMARY)])

        style.configure("TProgressbar", background=SURFACE_HIGH, troughcolor=SURFACE_CONTAINER,
                        bordercolor=SURFACE_CONTAINER, lightcolor=PRIMARY, darkcolor=PRIMARY)
        style.configure("Treeview", background=SURFACE_CONTAINER, fieldbackground=SURFACE_CONTAINER,
                        foreground=ON_SURFACE, rowheight=32, borderwidth=0,
                        bordercolor=SURFACE_CONTAINER, lightcolor=SURFACE_CONTAINER,
                        darkcolor=SURFACE_CONTAINER, relief="flat")
        style.map("Treeview", background=[("selected", PRIMARY)],
                  foreground=[("selected", ON_PRIMARY)],
                  bordercolor=[("focus", SURFACE_CONTAINER)],
                  lightcolor=[("focus", SURFACE_CONTAINER)],
                  darkcolor=[("focus", SURFACE_CONTAINER)])
        style.configure("Treeview.Heading", background=SURFACE_HIGH, foreground=ON_SURFACE_VARIANT,
                        font=("Segoe UI", 8, "bold"), relief="flat")
        style.map("Treeview.Heading", background=[("active", SURFACE_HIGH)])
        style.configure("Vertical.TScrollbar", background=SURFACE_HIGH,
                        troughcolor=SURFACE_CONTAINER, bordercolor=SURFACE_CONTAINER,
                        arrowcolor=ON_SURFACE_VARIANT, lightcolor=SURFACE_HIGH,
                        darkcolor=SURFACE_HIGH, borderwidth=0, arrowsize=12)
        style.map("Vertical.TScrollbar",
                  background=[("active", OUTLINE_VARIANT), ("!active", SURFACE_HIGH)],
                  arrowcolor=[("active", ON_SURFACE), ("!active", ON_SURFACE_VARIANT)])

    # ---------------------------------------------------------------- 布局
    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=0, minsize=340)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=0)
        self.rowconfigure(1, weight=1)

        self._build_topbar()
        self._build_sidebar()
        self._build_results()

    def _build_topbar(self) -> None:
        bar = ttk.Frame(self, style="Side.TFrame", padding=(20, 12))
        bar.grid(row=0, column=0, columnspan=2, sticky="ew")
        bar.columnconfigure(1, weight=1)

        ttk.Label(bar, text="VOB Splitter", style="Title.TLabel").grid(
            row=0, column=0, sticky="w")
        ttk.Label(bar, text="无损分割", style="MutedSide.TLabel").grid(
            row=0, column=1, sticky="w", padx=(10, 0))
        self.status_label = ttk.Label(bar, text="等待开始", style="MutedSide.TLabel")
        self.status_label.grid(row=0, column=2, sticky="e", padx=(0, 16))
        self.badge_label = ttk.Label(bar, text="未校验", style="BadgeIdle.TLabel", padding=(10, 4))
        self.badge_label.grid(row=0, column=3, sticky="e")

    def _build_sidebar(self) -> None:
        side = ttk.Frame(self, style="Side.TFrame", padding=(20, 16))
        side.grid(row=1, column=0, sticky="nsw")
        side.rowconfigure(0, weight=1)
        side.columnconfigure(0, weight=1)

        body = ttk.Frame(side, style="Side.TFrame")
        body.grid(row=0, column=0, sticky="nsew")

        row = 0
        # ---- 源 ----
        ttk.Label(body, text="源", style="Section.TLabel").grid(
            row=row, column=0, columnspan=2, sticky="w", pady=(0, 6))
        row += 1
        self.src_var = tk.StringVar()
        self.src_entry = ttk.Entry(body, textvariable=self.src_var)
        self.src_entry.grid(row=row, column=0, columnspan=2, sticky="ew")
        row += 1
        buttons = ttk.Frame(body, style="Side.TFrame")
        buttons.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        ttk.Button(buttons, text="选择文件…", style="Link.TButton",
                   command=self._pick_files).pack(side="left")
        ttk.Button(buttons, text="选择文件夹…", style="Link.TButton",
                   command=self._pick_dir).pack(side="left", padx=(8, 0))
        row += 1
        self.menu_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(body, text="包含菜单 VOB（VTS_xx_0.VOB）", variable=self.menu_var,
                        style="TCheckbutton").grid(row=row, column=0, columnspan=2,
                                                   sticky="w", pady=(6, 0))
        row += 1
        ttk.Separator(body, orient="horizontal").grid(row=row, column=0, columnspan=2,
                                                        sticky="ew", pady=16)
        row += 1

        # ---- 切分方式 ----
        ttk.Label(body, text="切分方式", style="Section.TLabel").grid(
            row=row, column=0, columnspan=2, sticky="w", pady=(0, 6))
        row += 1
        self.mode_var = tk.StringVar(value="auto")
        modes = ttk.Frame(body, style="Side.TFrame")
        modes.grid(row=row, column=0, columnspan=2, sticky="ew")
        for i, (value, text) in enumerate((("auto", "按章节"), ("duration", "等长"),
                                           ("times", "指定点"))):
            ttk.Radiobutton(modes, text=text, value=value, variable=self.mode_var,
                            command=self._sync_mode).pack(side="left", padx=(0, 12))
        row += 1
        self.mode_hint = ttk.Label(
            body,
            text="按 DVD 内置章节表切分。每章都是独立 MPEG-2 sequence，章首时间戳归零。",
            style="MutedSide.TLabel", wraplength=290, justify="left")
        self.mode_hint.grid(row=row, column=0, columnspan=2, sticky="w", pady=(8, 0))
        row += 1
        self.interval_var = tk.StringVar(value="600")
        self.times_var = tk.StringVar(value="")
        self.param_frame = ttk.Frame(body, style="Side.TFrame")
        self.param_frame.grid(row=row, column=0, columnspan=2, sticky="ew")
        ttk.Label(self.param_frame, text="每段秒数", style="MutedSide.TLabel").grid(
            row=0, column=0, sticky="w")
        self.interval_entry = ttk.Entry(self.param_frame, textvariable=self.interval_var,
                                        width=12)
        self.interval_entry.grid(row=0, column=1, sticky="e", padx=(8, 0))
        ttk.Label(self.param_frame, text="切点（秒或 00:01:30）", style="MutedSide.TLabel").grid(
            row=1, column=0, sticky="w", pady=(8, 0))
        self.times_entry = ttk.Entry(self.param_frame, textvariable=self.times_var, width=12)
        self.times_entry.grid(row=1, column=1, sticky="e", padx=(8, 0))
        row += 1
        ttk.Separator(body, orient="horizontal").grid(row=row, column=0, columnspan=2,
                                                        sticky="ew", pady=16)
        row += 1

        # ---- 输出 ----
        ttk.Label(body, text="输出", style="Section.TLabel").grid(
            row=row, column=0, columnspan=2, sticky="w", pady=(0, 6))
        row += 1
        self.out_var = tk.StringVar()
        ttk.Entry(body, textvariable=self.out_var).grid(row=row, column=0, columnspan=2,
                                                        sticky="ew")
        row += 1
        out_buttons = ttk.Frame(body, style="Side.TFrame")
        out_buttons.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        ttk.Button(out_buttons, text="选择输出目录…", style="Link.TButton",
                   command=self._pick_out).pack(side="left")
        row += 1
        self.fmt_var = tk.StringVar(value="vob")
        fmt = ttk.Frame(body, style="Side.TFrame")
        fmt.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        for value, text in (("vob", "VOB"), ("mkv", "MKV"), ("both", "两者")):
            ttk.Radiobutton(fmt, text=text, value=value, variable=self.fmt_var).pack(
                side="left", padx=(0, 12))
        row += 1
        ttk.Label(body, text="文件名前缀", style="MutedSide.TLabel").grid(
            row=row, column=0, sticky="w", pady=(8, 0))
        self.prefix_var = tk.StringVar(value="chapter")
        ttk.Entry(body, textvariable=self.prefix_var, width=12).grid(
            row=row, column=1, sticky="e", padx=(8, 0))
        row += 1
        ttk.Label(body, text="VOB 是字节级原样切出；MKV 需要 ffmpeg，只换容器不重编码。",
                  style="MutedSide.TLabel", wraplength=290, justify="left").grid(
            row=row, column=0, columnspan=2, sticky="w", pady=(8, 0))

        # ---- 底部：开始按钮 ----
        bottom = ttk.Frame(side, style="Side.TFrame", padding=(20, 16))
        bottom.grid(row=1, column=0, sticky="sew")
        self.run_button = ttk.Button(bottom, text="开始分割", style="Accent.TButton",
                                     command=self._start)
        self.run_button.pack(fill="x")
        self.progress = ttk.Progressbar(bottom, mode="determinate", maximum=1.0)
        self.progress.pack(fill="x", pady=(10, 0))

        self._sync_mode()

    def _build_results(self) -> None:
        right = ttk.Frame(self, style="TFrame", padding=(20, 16))
        right.grid(row=1, column=1, sticky="nsew")
        right.rowconfigure(0, weight=3)
        right.rowconfigure(1, weight=2)
        right.columnconfigure(0, weight=1)

        # ---- 章节表格 ----
        table_card = ttk.Frame(right, style="Card.TFrame")
        table_card.grid(row=0, column=0, sticky="nsew")
        table_card.rowconfigure(1, weight=1)
        table_card.columnconfigure(0, weight=1)

        head = ttk.Frame(table_card, style="Head.TFrame", padding=(12, 8))
        head.grid(row=0, column=0, columnspan=2, sticky="ew")
        ttk.Label(head, text="章节", style="Muted.TLabel").pack(side="left")
        self.table_hint = ttk.Label(head, text="", style="Muted.TLabel")
        self.table_hint.pack(side="right")

        columns = ("idx", "start", "dur", "size", "gop")
        self.tree = ttk.Treeview(table_card, columns=columns, show="headings", height=10)
        self.tree.heading("idx", text="章", anchor="w")
        self.tree.heading("start", text="起始", anchor="w")
        self.tree.heading("dur", text="时长", anchor="w")
        self.tree.heading("size", text="大小", anchor="w")
        self.tree.heading("gop", text="GOP", anchor="e")
        self.tree.column("idx", width=60, anchor="w", stretch=False)
        self.tree.column("start", width=150, anchor="w", stretch=False)
        self.tree.column("dur", width=150, anchor="w", stretch=False)
        self.tree.column("size", width=120, anchor="w", stretch=False)
        self.tree.column("gop", width=80, anchor="e", stretch=False)
        self.tree.grid(row=1, column=0, sticky="nsew", padx=(10, 0), pady=(0, 8))
        vsb = ttk.Scrollbar(table_card, orient="vertical", command=self.tree.yview,
                             style="Vertical.TScrollbar")
        vsb.grid(row=1, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=vsb.set)

        # 空状态提示（没有章节时显示）
        self.table_placeholder = ttk.Label(
            table_card,
            text="还没有章节\n选择 VOB 文件或目录后点「开始分割」，这里会列出检测到的每一章。",
            style="MutedCard.TLabel", justify="center")
        self.table_placeholder.place(relx=0.5, rely=0.62, anchor="center")

        # ---- 日志 ----
        log_card = ttk.Frame(right, style="Card.TFrame", padding=(0, 0))
        log_card.grid(row=1, column=0, sticky="nsew", pady=(16, 0))
        log_card.rowconfigure(1, weight=1)
        log_card.columnconfigure(0, weight=1)

        log_head = ttk.Frame(log_card, style="Head.TFrame", padding=(12, 8))
        log_head.grid(row=0, column=0, columnspan=2, sticky="ew")
        ttk.Label(log_head, text="日志", style="Muted.TLabel").pack(side="left")

        self.log = tk.Text(log_card, bg=SURFACE_CONTAINER, fg=ON_SURFACE_VARIANT,
                           insertbackground=ON_SURFACE, relief="flat", bd=0,
                           font=MONO, wrap="none", padx=12, pady=10)
        self.log.grid(row=1, column=0, sticky="nsew")
        lsb = ttk.Scrollbar(log_card, orient="vertical", command=self.log.yview,
                             style="Vertical.TScrollbar")
        lsb.grid(row=1, column=1, sticky="ns")
        self.log.configure(yscrollcommand=lsb.set)
        self.log.configure(state="disabled")
        self._append_log("运行日志会出现在这里")

    # ---------------------------------------------------------------- 交互
    def _sync_mode(self) -> None:
        mode = self.mode_var.get()
        # 只有需要时才显示参数框，避免界面里出现用不上的输入框
        if mode == "duration":
            self.param_frame.grid()
            self.interval_entry.configure(state="normal")
            self.times_entry.configure(state="disabled")
        elif mode == "times":
            self.param_frame.grid()
            self.interval_entry.configure(state="disabled")
            self.times_entry.configure(state="normal")
        else:
            self.param_frame.grid_remove()
        if mode == "auto":
            self.mode_hint.configure(
                text="按 DVD 内置章节表切分。每章都是独立 MPEG-2 sequence，章首时间戳归零。")
        elif mode == "duration":
            self.mode_hint.configure(text="按固定时长切分，切点吸附到最近的随机访问点。")
        else:
            self.mode_hint.configure(text="按指定时间点切分，支持 90 / 1:30 / 00:01:30.5 / 1h2m3s。")

    def _pick_files(self) -> None:
        paths = filedialog.askopenfilenames(
            title="选择 VOB 文件",
            filetypes=[("VOB 文件", "*.vob"), ("所有文件", "*.*")])
        if paths:
            self.src_var.set(";".join(paths))

    def _pick_dir(self) -> None:
        path = filedialog.askdirectory(title="选择包含 VOB 的目录")
        if path:
            self.src_var.set(path)

    def _pick_out(self) -> None:
        path = filedialog.askdirectory(title="选择输出目录")
        if path:
            self.out_var.set(path)

    def _append_log(self, message: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", message + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _set_chapters(self, chapters: List[Chapter]) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        for ch in chapters:
            self.tree.insert("", "end", values=(
                "%02d" % (ch.index + 1),
                _fmt_time(ch.global_start if ch.global_start else ch.start_pts),
                _fmt_time(ch.duration),
                _fmt_size(ch.size),
                ch.rap_count,
            ))
        if chapters:
            self.table_placeholder.place_forget()
        else:
            self.table_placeholder.place(relx=0.5, rely=0.62, anchor="center")

    def _resolve_sources(self) -> List[str]:
        raw = [p.strip() for p in self.src_var.get().split(";") if p.strip()]
        out: List[str] = []
        for p in raw:
            if os.path.isdir(p):
                vobs = sorted(f for f in os.listdir(p) if f.lower().endswith(".vob"))
                vobs.sort(key=lambda n: (_vob_key(n)))
                for v in vobs:
                    if not self.menu_var.get() and _is_menu_vob(v):
                        continue
                    out.append(os.path.join(p, v))
            else:
                out.append(p)
        return out

    # ---------------------------------------------------------------- 运行
    def _start(self) -> None:
        if self._running:
            return
        files = self._resolve_sources()
        if not files:
            self._append_log("错误：请先选择 VOB 文件或目录")
            return
        missing = [f for f in files if not os.path.isfile(f)]
        if missing:
            self._append_log("错误：文件不存在 %s" % missing[0])
            return
        if not self.out_var.get().strip():
            self._append_log("错误：请先选择输出目录")
            return

        mode = self.mode_var.get()
        try:
            if mode == "duration":
                spec = ChapterSpec.duration(float(self.interval_var.get() or 600))
            elif mode == "times":
                spec = ChapterSpec.times(parse_time_list(self.times_var.get()))
            else:
                spec = ChapterSpec.auto()
        except ValueError as exc:
            self._append_log("错误：%s" % exc)
            return

        self._running = True
        self._verdict = None
        self.badge_label.configure(text="校验中…", style="BadgeIdle.TLabel")
        self.run_button.configure(state="disabled")
        self.progress.configure(value=0.0)
        for item in self.tree.get_children():
            self.tree.delete(item)
        self._append_log("开始处理…")

        out_dir = self.out_var.get().strip()
        prefix = self.prefix_var.get().strip() or "chapter"
        fmt = self.fmt_var.get()

        def worker() -> None:
            try:
                handlers = Handlers(
                    log=lambda m: self._queue.put(("log", m)),
                    progress=lambda v, m: self._queue.put(("progress", (v, m))),
                    chapters=lambda c: self._queue.put(("chapters", c)),
                )
                result = run_split(files, spec, out_dir, prefix=prefix, output_format=fmt,
                                   handlers=handlers)
                self._queue.put(("done", result))
            except Exception as exc:                     # noqa: BLE001
                self._queue.put(("error", str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _poll(self) -> None:
        while True:
            try:
                kind, payload = self._queue.get_nowait()
            except queue.Empty:
                break
            if kind == "log":
                self._append_log(payload)
            elif kind == "progress":
                value, message = payload
                self.progress.configure(value=max(0.0, min(1.0, value)))
                self.status_label.configure(text=message)
            elif kind == "chapters":
                self._set_chapters(payload)
                self.table_hint.configure(text="%d 章" % len(payload))
            elif kind == "done":
                self._on_done(payload)
            elif kind == "error":
                self._running = False
                self.run_button.configure(state="normal")
                self.status_label.configure(text="失败")
                self.badge_label.configure(text="校验未通过", style="BadgeFail.TLabel")
                self._append_log("错误：%s" % payload)
        # 必须无条件续期：空闲时链子一断，后面点「开始分割」就再也没人消费队列了，
        # 界面会看起来完全没反应。
        self.after(80, self._poll)

    def _on_done(self, result: RunResult) -> None:
        self._running = False
        self.run_button.configure(state="normal")
        self.progress.configure(value=1.0)
        self._set_chapters(result.chapters)
        self.table_hint.configure(text="%d 章" % len(result.chapters))
        self._verdict = result.verified
        if result.verified:
            self.badge_label.configure(text="无损校验通过", style="Badge.TLabel")
            self.status_label.configure(text="完成 · 无损校验通过")
        else:
            self.badge_label.configure(text="校验未通过", style="BadgeFail.TLabel")
            self.status_label.configure(text="完成 · 校验未通过")
        if result.saw_no_chapters:
            self.table_hint.configure(text="没有检测到章节边界")


def _vob_key(name: str):
    stem = os.path.splitext(name)[0]
    parts = stem.split("_")
    try:
        return (parts[-2] if len(parts) >= 2 else stem, int(parts[-1]))
    except (ValueError, IndexError):
        return (stem, 0)


def _is_menu_vob(name: str) -> bool:
    parts = os.path.splitext(name)[0].split("_")
    if len(parts) < 3:
        return False
    try:
        return int(parts[-1]) == 0
    except ValueError:
        return False


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--selftest" in argv:
        # 冒烟测试：建出界面并立刻退出（用于 CI 检查没有语法/构造错误）
        app = VobSplitterApp()
        app.update_idletasks()
        app.destroy()
        print("gui selftest ok")
        return 0
    app = VobSplitterApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
