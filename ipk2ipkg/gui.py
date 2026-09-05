"""Windows GUI for converting OpenWrt IPK files into iKuai 4.0 IPKG packages."""

from __future__ import annotations

import base64
import os
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import __app_name__, __version__
from .builder import IpkgSpec, normalize_version, sanitize_name
from .convert import convert_ipks, suggest_spec
from .icon import make_logo_png
from .parser import IpkError, IpkPackage, load_ipk


BG = "#f4f7fb"
HEADER = "#0d6efd"
HEADER_TEXT = "#ffffff"
CARD = "#ffffff"
TEXT = "#1b2430"
MUTED = "#5c6b7a"
ACCENT = "#0d6efd"


def _png_photo(png: bytes) -> tk.PhotoImage:
    return tk.PhotoImage(data=base64.b64encode(png).decode("ascii"))


class ScrollFrame(ttk.Frame):
    """Vertical scroll container so short windows still show all form fields."""

    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent, style="Card.TFrame")
        self.canvas = tk.Canvas(self, bg=CARD, highlightthickness=0, bd=0)
        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas, style="Card.TFrame")
        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.vsb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.vsb.pack(side="right", fill="y")
        self.inner.bind("<Configure>", self._on_inner)
        self.canvas.bind("<Configure>", self._on_canvas)
        self.inner.bind("<Enter>", self._bind_wheel)
        self.inner.bind("<Leave>", self._unbind_wheel)
        self.canvas.bind("<Enter>", self._bind_wheel)
        self.canvas.bind("<Leave>", self._unbind_wheel)

    def _on_inner(self, _event=None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas(self, event) -> None:
        self.canvas.itemconfigure(self._win, width=event.width)

    def _bind_wheel(self, _event=None) -> None:
        self.canvas.bind_all("<MouseWheel>", self._on_wheel)

    def _unbind_wheel(self, _event=None) -> None:
        self.canvas.unbind_all("<MouseWheel>")

    def _on_wheel(self, event) -> None:
        self.canvas.yview_scroll(int(-event.delta / 120), "units")


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{__app_name__} {__version__}")
        self.geometry("980x680")
        self.minsize(760, 480)
        self.configure(bg=BG)
        self.ipk_paths: list[Path] = []
        self.packages: list[IpkPackage] = []
        self._busy = False
        self._init_style()
        self._build()
        self._load_argv_files()

    def _init_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background=CARD)
        style.configure("TLabel", background=BG, foreground=TEXT, font=("Microsoft YaHei UI", 10))
        style.configure("Card.TLabel", background=CARD, foreground=TEXT, font=("Microsoft YaHei UI", 10))
        style.configure("Muted.TLabel", background=CARD, foreground=MUTED, font=("Microsoft YaHei UI", 9))
        style.configure("Header.TLabel", background=HEADER, foreground=HEADER_TEXT, font=("Microsoft YaHei UI", 16, "bold"))
        style.configure("Sub.TLabel", background=HEADER, foreground="#dbe8ff", font=("Microsoft YaHei UI", 9))
        style.configure("TButton", font=("Microsoft YaHei UI", 10), padding=6)
        style.configure("Accent.TButton", font=("Microsoft YaHei UI", 11, "bold"), padding=(18, 8))
        style.configure("TEntry", fieldbackground="#fff", padding=4)
        style.configure("TCheckbutton", background=CARD, font=("Microsoft YaHei UI", 10))
        style.configure("Treeview", font=("Microsoft YaHei UI", 9), rowheight=24, background=CARD, fieldbackground=CARD)
        style.configure("Treeview.Heading", font=("Microsoft YaHei UI", 9, "bold"))
        style.configure("Footer.TFrame", background="#e8eef6")
        style.configure("Footer.TLabel", background="#e8eef6", foreground=MUTED, font=("Microsoft YaHei UI", 10))

    def _build(self) -> None:
        self._logo = _png_photo(make_logo_png(64))
        self._icon = _png_photo(make_logo_png(32))
        try:
            self.iconphoto(True, self._logo, self._icon)
        except tk.TclError:
            pass

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        header = tk.Frame(self, bg=HEADER)
        header.grid(row=0, column=0, sticky="ew")
        tk.Label(header, image=self._logo, bg=HEADER, bd=0).pack(side="left", padx=(16, 12), pady=10)
        texts = tk.Frame(header, bg=HEADER)
        texts.pack(side="left", fill="x", expand=True, pady=10)
        ttk.Label(texts, text="爱快 IPK → IPKG 转换工具", style="Header.TLabel").pack(anchor="w")
        ttk.Label(
            texts,
            text="把 OpenWrt 的 .ipk 封装成爱快 4.0 应用市场可本地安装的 .ipkg（Docker 应用）",
            style="Sub.TLabel",
        ).pack(anchor="w", pady=(2, 0))

        body = ttk.Frame(self)
        body.grid(row=1, column=0, sticky="nsew", padx=16, pady=(12, 8))
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        left = ttk.Frame(body, style="Card.TFrame")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        right_wrap = ScrollFrame(body)
        right_wrap.grid(row=0, column=1, sticky="nsew")

        self._build_file_panel(left)
        self._build_meta_panel(right_wrap.inner)

        log_wrap = ttk.Frame(self, style="Card.TFrame")
        log_wrap.grid(row=2, column=0, sticky="ew", padx=16)
        ttk.Label(log_wrap, text="日志", style="Card.TLabel", font=("Microsoft YaHei UI", 10, "bold")).pack(
            anchor="w", padx=12, pady=(6, 2)
        )
        self.log = tk.Text(log_wrap, height=5, font=("Consolas", 9), relief="flat", bg="#0f1724", fg="#d7e3f4")
        self.log.pack(fill="x", padx=12, pady=(0, 8))
        self.log.configure(state="disabled")

        bar = tk.Frame(self, bg="#e8eef6")
        bar.grid(row=3, column=0, sticky="ew")
        inner_bar = ttk.Frame(bar, style="Footer.TFrame")
        inner_bar.pack(fill="x", padx=16, pady=10)
        ttk.Button(inner_bar, text="打开输出目录", command=self._open_output).pack(side="left")
        self.status = ttk.Label(inner_bar, text="就绪", style="Footer.TLabel")
        self.status.pack(side="left", padx=12)
        self.convert_btn = ttk.Button(inner_bar, text="开始转换", style="Accent.TButton", command=self._convert)
        self.convert_btn.pack(side="right")

    def _card_title(self, parent: ttk.Frame, text: str) -> None:
        ttk.Label(parent, text=text, style="Card.TLabel", font=("Microsoft YaHei UI", 11, "bold")).pack(
            anchor="w", padx=12, pady=(12, 6)
        )

    def _build_file_panel(self, parent: ttk.Frame) -> None:
        self._card_title(parent, "1. 选择 IPK 文件")
        ttk.Label(parent, text="可一次加入多个 IPK，会合并进同一个应用包。", style="Muted.TLabel").pack(
            anchor="w", padx=12
        )
        btns = ttk.Frame(parent, style="Card.TFrame")
        btns.pack(fill="x", padx=12, pady=8)
        ttk.Button(btns, text="添加 IPK…", command=self._add_files).pack(side="left")
        ttk.Button(btns, text="移除选中", command=self._remove_selected).pack(side="left", padx=6)
        ttk.Button(btns, text="清空", command=self._clear_files).pack(side="left")

        columns = ("name", "package", "version", "arch")
        self.tree = ttk.Treeview(parent, columns=columns, show="headings", height=5)
        self.tree.heading("name", text="文件")
        self.tree.heading("package", text="包名")
        self.tree.heading("version", text="版本")
        self.tree.heading("arch", text="架构")
        self.tree.column("name", width=180)
        self.tree.column("package", width=120)
        self.tree.column("version", width=80)
        self.tree.column("arch", width=80)
        self.tree.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        self.warn_var = tk.StringVar(value="")
        ttk.Label(parent, textvariable=self.warn_var, style="Muted.TLabel", wraplength=430).pack(
            fill="x", padx=12, pady=(0, 8)
        )

        self._card_title(parent, "检测到的可执行文件")
        self.exe_list = tk.Listbox(parent, height=4, font=("Consolas", 9), relief="solid", borderwidth=1)
        self.exe_list.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.exe_list.bind("<Double-Button-1>", self._use_selected_exe)

    def _build_meta_panel(self, parent: ttk.Frame) -> None:
        self._card_title(parent, "2. 应用信息（可改）")
        form = ttk.Frame(parent, style="Card.TFrame")
        form.pack(fill="x", padx=12)

        self.vars = {
            "name": tk.StringVar(),
            "display_name": tk.StringVar(),
            "version": tk.StringVar(value="1.0.0"),
            "maintainer": tk.StringVar(value="ipk2ipkg"),
            "image": tk.StringVar(value="alpine:3.20"),
            "command": tk.StringVar(),
            "host_port": tk.StringVar(value="8080"),
            "container_port": tk.StringVar(value="8080"),
            "output": tk.StringVar(),
        }
        self.host_network = tk.BooleanVar(value=False)
        self.description = tk.Text(parent, height=3, font=("Microsoft YaHei UI", 9), relief="solid", borderwidth=1)

        rows = [
            ("内部名称", "name"),
            ("显示名称", "display_name"),
            ("版本 (x.y.z)", "version"),
            ("维护者", "maintainer"),
            ("Docker 镜像", "image"),
            ("启动命令", "command"),
            ("Web 端口", "host_port"),
            ("容器端口", "container_port"),
            ("输出目录", "output"),
        ]
        for i, (label, key) in enumerate(rows):
            ttk.Label(form, text=label, style="Card.TLabel").grid(row=i, column=0, sticky="w", pady=3)
            entry = ttk.Entry(form, textvariable=self.vars[key], width=36)
            entry.grid(row=i, column=1, sticky="ew", padx=(8, 0), pady=3)
            if key == "output":
                ttk.Button(form, text="浏览", command=self._browse_output).grid(row=i, column=2, padx=6)
        form.columnconfigure(1, weight=1)

        ttk.Checkbutton(parent, text="使用 host 网络（不映射端口）", variable=self.host_network).pack(
            anchor="w", padx=12, pady=(8, 4)
        )
        ttk.Label(parent, text="描述", style="Card.TLabel").pack(anchor="w", padx=12)
        self.description.pack(fill="x", padx=12, pady=(0, 12))

    def _log(self, message: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", message.rstrip() + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _load_argv_files(self) -> None:
        files = [Path(p) for p in sys.argv[1:] if Path(p).is_file() and Path(p).suffix.lower() in {".ipk", ".ipkg"}]
        if files:
            self._ingest(files)

    def _add_files(self) -> None:
        files = filedialog.askopenfilenames(
            title="选择 IPK 文件",
            filetypes=[("IPK 包", "*.ipk"), ("IPKG 包", "*.ipkg"), ("所有文件", "*.*")],
        )
        if files:
            self._ingest([Path(f) for f in files])

    def _ingest(self, files: list[Path]) -> None:
        for path in files:
            if path in self.ipk_paths:
                continue
            try:
                pkg = load_ipk(path)
            except IpkError as exc:
                messagebox.showerror("无法解析", f"{path.name}\n{exc}")
                continue
            self.ipk_paths.append(path)
            self.packages.append(pkg)
            self.tree.insert(
                "",
                "end",
                iid=str(path),
                values=(path.name, pkg.control.package or "-", pkg.control.version or "-", pkg.control.architecture or "-"),
            )
            self._log(f"已加载 {path.name}  ({pkg.kind})")
            if pkg.warning:
                self._log("警告: " + pkg.warning)
        self._refresh_from_packages()

    def _remove_selected(self) -> None:
        selected = self.tree.selection()
        remain_paths: list[Path] = []
        remain_pkgs: list[IpkPackage] = []
        remove = {Path(i) for i in selected}
        for path, pkg in zip(self.ipk_paths, self.packages):
            if path in remove:
                self.tree.delete(str(path))
            else:
                remain_paths.append(path)
                remain_pkgs.append(pkg)
        self.ipk_paths = remain_paths
        self.packages = remain_pkgs
        self._refresh_from_packages()

    def _clear_files(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self.ipk_paths.clear()
        self.packages.clear()
        self.exe_list.delete(0, "end")
        self.warn_var.set("")

    def _refresh_from_packages(self) -> None:
        self.exe_list.delete(0, "end")
        warnings = [p.warning for p in self.packages if p.warning]
        self.warn_var.set("；".join(warnings))
        if not self.packages:
            return
        try:
            spec = suggest_spec(self.packages)
        except IpkError:
            return
        self.vars["name"].set(spec.name)
        self.vars["display_name"].set(spec.display_name)
        self.vars["version"].set(spec.version)
        self.vars["maintainer"].set(spec.maintainer)
        self.vars["command"].set(spec.command)
        self.vars["host_port"].set(str(spec.host_port))
        self.vars["container_port"].set(str(spec.container_port))
        if not self.vars["output"].get():
            self.vars["output"].set(str(self.ipk_paths[0].parent))
        self.description.delete("1.0", "end")
        self.description.insert("1.0", spec.description)
        seen = []
        for pkg in self.packages:
            for exe in pkg.executables:
                if exe not in seen:
                    seen.append(exe)
                    self.exe_list.insert("end", exe)

    def _use_selected_exe(self, _event=None) -> None:
        sel = self.exe_list.curselection()
        if not sel:
            return
        rel = self.exe_list.get(sel[0])
        self.vars["command"].set(f"/opt/pkg/{rel.replace(chr(92), '/')}")

    def _browse_output(self) -> None:
        folder = filedialog.askdirectory(title="选择输出目录")
        if folder:
            self.vars["output"].set(folder)

    def _open_output(self) -> None:
        folder = self.vars["output"].get().strip()
        if not folder:
            messagebox.showinfo("提示", "还没有设置输出目录")
            return
        path = Path(folder)
        if not path.exists():
            messagebox.showerror("错误", "输出目录不存在")
            return
        try:
            os.startfile(path)  # type: ignore[attr-defined]
        except OSError as exc:
            messagebox.showerror("错误", str(exc))

    def _collect_spec(self) -> IpkgSpec:
        try:
            host_port = int(self.vars["host_port"].get().strip() or "8080")
            container_port = int(self.vars["container_port"].get().strip() or str(host_port))
        except ValueError as exc:
            raise IpkError("端口必须是数字") from exc
        return IpkgSpec(
            name=sanitize_name(self.vars["name"].get()),
            display_name=self.vars["display_name"].get().strip() or sanitize_name(self.vars["name"].get()),
            version=normalize_version(self.vars["version"].get()),
            description=self.description.get("1.0", "end").strip(),
            maintainer=self.vars["maintainer"].get().strip() or "ipk2ipkg",
            image=self.vars["image"].get().strip() or "alpine:3.20",
            command=self.vars["command"].get().strip(),
            host_port=host_port,
            container_port=container_port,
            host_network=self.host_network.get(),
        )

    def _convert(self) -> None:
        if self._busy:
            return
        if not self.ipk_paths:
            messagebox.showwarning("提示", "请先添加 IPK 文件")
            return
        output = self.vars["output"].get().strip()
        if not output:
            messagebox.showwarning("提示", "请选择输出目录")
            return
        try:
            spec = self._collect_spec()
        except IpkError as exc:
            messagebox.showerror("参数错误", str(exc))
            return
        self._busy = True
        self.convert_btn.configure(state="disabled")
        self.status.configure(text="正在转换…")
        self._log("开始转换…")

        def worker() -> None:
            try:
                result = convert_ipks(self.ipk_paths, output, spec=spec)
                self.after(0, lambda: self._done(result, None))
            except Exception as exc:  # noqa: BLE001
                self.after(0, lambda: self._done(None, exc))

        threading.Thread(target=worker, daemon=True).start()

    def _done(self, result, error: Exception | None) -> None:
        self._busy = False
        self.convert_btn.configure(state="normal")
        if error is not None:
            self.status.configure(text="转换失败")
            self._log(f"失败: {error}")
            messagebox.showerror("转换失败", str(error))
            return
        for warning in result.warnings:
            self._log("警告: " + warning)
        self._log(f"已生成: {result.output}")
        self.status.configure(text="完成")
        messagebox.showinfo("完成", f"已生成 IPKG：\n{result.output}\n\n到爱快：高级应用 → 应用市场 → 本地安装")


def run_gui() -> None:
    app = App()
    app.mainloop()
