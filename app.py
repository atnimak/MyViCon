"""MyViCon — GUI для объединения серий (видео + озвучки + субтитры + шрифты) через mkvmerge.

Запуск:  python app.py
Зависимости: только стандартная библиотека Python (tkinter входит в состав).
"""

import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from models import AppConfig, Source, program_dir
from merger import build_plan, run_merge

APP_TITLE = "MyViCon — сборка серий (mkvmerge)"


def resource_path(name):
    """Путь к ресурсу, вложенному в сборку.

    В .exe (PyInstaller --onefile) файлы распаковываются в sys._MEIPASS,
    при запуске из исходников — берутся из папки скрипта.
    """
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def default_tool_path(exe_name):
    """Ожидаемый путь к инструменту MKVToolNix рядом с программой.

    Например: <папка программы>/mkvtoolnix/mkvmerge.exe
    """
    return os.path.join(program_dir(), "mkvtoolnix", exe_name)


class SourceDialog(tk.Toplevel):
    """Диалог добавления/редактирования источника (озвучка или субтитры)."""

    def __init__(self, parent, title, source=None, app=None):
        super().__init__(parent)
        self.title(title)
        self.transient(parent)
        self.resizable(False, False)
        self.result = None
        self.app = app

        src = source or Source()

        self.var_dir = tk.StringVar(value=src.dir)
        self.var_name = tk.StringVar(value=src.name)
        self.var_lang = tk.StringVar(value=src.language or "rus")
        self.var_default = tk.BooleanVar(value=src.default)

        frm = ttk.Frame(self, padding=12)
        frm.grid(row=0, column=0, sticky="nsew")

        ttk.Label(frm, text="Папка с файлами:").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(frm, textvariable=self.var_dir, width=48).grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Button(frm, text="Обзор…", command=self._browse).grid(row=0, column=2, padx=(6, 0), pady=4)

        ttk.Label(frm, text="Имя дорожки:").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(frm, textvariable=self.var_name, width=48).grid(row=1, column=1, columnspan=2, sticky="ew", pady=4)

        ttk.Label(frm, text="Язык (ISO, напр. rus/jpn/eng):").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Entry(frm, textvariable=self.var_lang, width=12).grid(row=2, column=1, sticky="w", pady=4)

        ttk.Checkbutton(frm, text="Дорожка по умолчанию", variable=self.var_default).grid(
            row=3, column=1, sticky="w", pady=4)

        btns = ttk.Frame(frm)
        btns.grid(row=4, column=0, columnspan=3, sticky="e", pady=(10, 0))
        ttk.Button(btns, text="OK", command=self._ok).pack(side="right", padx=4)
        ttk.Button(btns, text="Отмена", command=self.destroy).pack(side="right")

        frm.columnconfigure(1, weight=1)
        self.bind("<Return>", lambda e: self._ok())
        self.bind("<Escape>", lambda e: self.destroy())
        self._center()
        self.grab_set()
        self.wait_window()

    def _center(self):
        self.update_idletasks()
        w = self.winfo_width()
        h = self.winfo_height()
        x = (self.winfo_screenwidth() - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"+{x}+{y}")

    def _browse(self):
        start = self.var_dir.get() or (self.app.last_dir if self.app else "") or os.getcwd()
        d = filedialog.askdirectory(title="Выберите папку", initialdir=start)
        if d:
            self.var_dir.set(d)
            if self.app:
                self.app.last_dir = d
            if not self.var_name.get():
                self.var_name.set(os.path.basename(d.rstrip("/\\")))

    def _ok(self):
        if not self.var_dir.get().strip():
            messagebox.showwarning("MyViCon", "Укажите папку с файлами.", parent=self)
            return
        self.result = Source(
            dir=self.var_dir.get().strip(),
            name=self.var_name.get().strip(),
            language=self.var_lang.get().strip() or "und",
            default=self.var_default.get(),
        )
        self.destroy()


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.withdraw()  # скрываем, чтобы не мелькало в углу до центрирования
        self.title(APP_TITLE)
        self._set_icon()
        self.minsize(820, 620)
        self._center_window(980, 760)

        self.config_data = AppConfig.load()
        # По умолчанию ищем инструменты рядом с программой: mkvtoolnix/*.exe
        if not self.config_data.mkvmerge:
            self.config_data.mkvmerge = default_tool_path("mkvmerge.exe")
        if not self.config_data.mkvpropedit:
            self.config_data.mkvpropedit = default_tool_path("mkvpropedit.exe")
        self.log_queue = queue.Queue()
        self.worker = None
        self._stop = False
        self._fallback_notified = False
        self._prev_video = ""
        self.last_dir = self.config_data.last_dir or os.getcwd()

        self._build_ui()
        self._load_into_ui()
        self.after(100, self._drain_log)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.deiconify()  # показываем уже по центру

    def _center_window(self, w, h):
        x = (self.winfo_screenwidth() - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _set_icon(self):
        # Windows: назначаем собственный AppUserModelID, иначе в панели задач
        # показывается иконка интерпретатора Python, а не окна.
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("MyViCon.App")
            except Exception:  # noqa: BLE001
                pass
        icon = resource_path("icon.ico")
        if os.path.isfile(icon):
            try:
                # default=... применяет иконку к главному окну и дочерним Toplevel.
                self.iconbitmap(default=icon)
            except Exception:  # noqa: BLE001 — несовместимая иконка не критична
                pass

    # ---------- построение интерфейса ----------
    def _build_ui(self):
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=(8, 0))

        self.tab_settings = ttk.Frame(nb)
        self.tab_result = ttk.Frame(nb)
        nb.add(self.tab_settings, text="Источники и настройки")
        nb.add(self.tab_result, text="Предпросмотр и лог")

        self._build_settings_tab(self.tab_settings)
        self._build_result_tab(self.tab_result)

        # Нижняя панель управления (вне вкладок — видна всегда)
        bar = ttk.Frame(self, padding=8)
        bar.pack(fill="x")
        self.status_var = tk.StringVar(value="Готово.")
        ttk.Label(bar, textvariable=self.status_var).pack(side="left")

        self.progress_var = tk.DoubleVar(value=0)
        self.progress = ttk.Progressbar(bar, orient="horizontal", mode="determinate",
                                        length=220, maximum=100, variable=self.progress_var)
        self.progress.pack(side="left", padx=(12, 0))
        self.progress_label_var = tk.StringVar(value="")
        ttk.Label(bar, textvariable=self.progress_label_var).pack(side="left", padx=(6, 0))

        self.btn_run = ttk.Button(bar, text="Собрать", command=self._on_run)
        self.btn_run.pack(side="right", padx=(6, 0))
        self.btn_stop = ttk.Button(bar, text="Стоп", command=self._on_stop, state="disabled")
        self.btn_stop.pack(side="right", padx=(6, 0))
        ttk.Button(bar, text="Предпросмотр", command=self._on_preview).pack(side="right", padx=(6, 0))
        ttk.Button(bar, text="Сохранить настройки", command=self._save_config).pack(side="right", padx=(6, 0))

    def _build_settings_tab(self, parent):
        canvas = tk.Canvas(parent, highlightthickness=0)
        scroll = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas)
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        pad = dict(padx=8, pady=4)

        # --- Инструменты ---
        g_tools = ttk.LabelFrame(inner, text="Инструменты MKVToolNix", padding=8)
        g_tools.pack(fill="x", **pad)
        self.var_mkvmerge = tk.StringVar()
        self.var_mkvpropedit = tk.StringVar()
        self.var_mkvmerge_status = tk.StringVar()
        self.var_mkvpropedit_status = tk.StringVar()
        self.entry_mkvmerge = self._path_row(
            g_tools, 0, "mkvmerge.exe:", self.var_mkvmerge, is_file=True,
            status_var=self.var_mkvmerge_status)
        self.entry_mkvpropedit = self._path_row(
            g_tools, 1, "mkvpropedit.exe (для шрифтов):", self.var_mkvpropedit, is_file=True,
            status_var=self.var_mkvpropedit_status)
        ttk.Label(g_tools, text="Ожидаются в <папка программы>\\mkvtoolnix\\ рядом с exe/py.",
                  foreground="#666").grid(row=2, column=1, sticky="w")
        g_tools.columnconfigure(1, weight=1)

        # Стиль для подсветки несуществующих путей
        style = ttk.Style(self)
        style.configure("Invalid.TEntry", fieldbackground="#ffe5e5", foreground="#b00020")
        self.var_mkvmerge.trace_add("write", lambda *a: self._update_tool_status())
        self.var_mkvpropedit.trace_add("write", lambda *a: self._update_tool_status())

        # --- Папки ---
        g_dirs = ttk.LabelFrame(inner, text="Папки", padding=8)
        g_dirs.pack(fill="x", **pad)
        self.var_video = tk.StringVar()
        self.var_output = tk.StringVar()
        self.var_fonts = tk.StringVar()
        self._path_row(g_dirs, 0, "Оригиналы (видео):", self.var_video)
        self._path_row(g_dirs, 1, "Папка вывода:", self.var_output)
        self._path_row(g_dirs, 2, "Шрифты (опц.):", self.var_fonts)
        ttk.Label(g_dirs, text="Пусто = <папка видео>\\Merged (создаётся при сборке).",
                  foreground="#666").grid(row=3, column=1, sticky="w")
        self.var_video.trace_add("write", self._on_video_changed)
        ttk.Button(g_dirs, text="✕ Очистить", command=self._clear_dirs).grid(
            row=3, column=2, sticky="e", pady=(6, 0))
        g_dirs.columnconfigure(1, weight=1)

        # --- Озвучки ---
        self.audio_tree = self._build_source_group(inner, "Источники озвучки", "audio")
        # --- Субтитры ---
        self.sub_tree = self._build_source_group(inner, "Источники субтитров", "subtitle")

        # --- Сопоставление / шаблоны ---
        g_match = ttk.LabelFrame(inner, text="Сопоставление и имена", padding=8)
        g_match.pack(fill="x", **pad)
        self.var_regex = tk.StringVar()
        self.var_out_tpl = tk.StringVar()
        self.var_title_tpl = tk.StringVar()

        ttk.Label(g_match, text="Своя регулярка для № серии (опц.):").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(g_match, textvariable=self.var_regex).grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Label(g_match, text="Пусто = авто (S01E05, EP05, «- 05», отдельное число).",
                  foreground="#666").grid(row=1, column=1, sticky="w")

        ttk.Label(g_match, text="Шаблон имени файла:").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Entry(g_match, textvariable=self.var_out_tpl).grid(row=2, column=1, sticky="ew", pady=4)
        ttk.Label(g_match, text="Шаблон заголовка (--title):").grid(row=3, column=0, sticky="w", pady=4)
        ttk.Entry(g_match, textvariable=self.var_title_tpl).grid(row=3, column=1, sticky="ew", pady=4)
        ttk.Label(g_match, text="Доступно: {base} — имя видео без расширения, {episode} — номер серии.",
                  foreground="#666").grid(row=4, column=1, sticky="w")
        g_match.columnconfigure(1, weight=1)

    def _build_source_group(self, parent, title, kind):
        g = ttk.LabelFrame(parent, text=title, padding=8)
        g.pack(fill="x", padx=8, pady=4)

        cols = ("dir", "name", "language", "default")
        tree = ttk.Treeview(g, columns=cols, show="headings", height=4)
        tree.heading("dir", text="Папка")
        tree.heading("name", text="Имя дорожки")
        tree.heading("language", text="Язык")
        tree.heading("default", text="По умолч.")
        tree.column("dir", width=420)
        tree.column("name", width=180)
        tree.column("language", width=60, anchor="center")
        tree.column("default", width=70, anchor="center")
        tree.grid(row=0, column=0, rowspan=4, sticky="ew")
        g.columnconfigure(0, weight=1)

        tree.sources = []  # прикрепляем список Source к дереву
        tree.kind = kind
        tree.bind("<Double-1>", lambda e, t=tree: self._edit_source(t))

        ttk.Button(g, text="Добавить", command=lambda t=tree: self._add_source(t)).grid(row=0, column=1, sticky="ew", padx=(6, 0))
        ttk.Button(g, text="Изменить", command=lambda t=tree: self._edit_source(t)).grid(row=1, column=1, sticky="ew", padx=(6, 0))
        ttk.Button(g, text="Удалить", command=lambda t=tree: self._remove_source(t)).grid(row=2, column=1, sticky="ew", padx=(6, 0))
        ttk.Button(g, text="✕ Очистить", command=lambda t=tree: self._clear_sources(t)).grid(row=3, column=1, sticky="ew", padx=(6, 0))
        return tree

    def _build_result_tab(self, parent):
        # Предпросмотр совпадений
        g_prev = ttk.LabelFrame(parent, text="Предпросмотр совпадений", padding=6)
        g_prev.pack(fill="both", expand=True, padx=8, pady=(8, 4))

        cols = ("episode", "video", "audio", "subs", "status")
        self.preview_tree = ttk.Treeview(g_prev, columns=cols, show="headings", height=10)
        for c, txt, w in [("episode", "Серия", 60), ("video", "Видео", 300),
                          ("audio", "Озвучки", 160), ("subs", "Субтитры", 160),
                          ("status", "Статус", 120)]:
            self.preview_tree.heading(c, text=txt)
            self.preview_tree.column(c, width=w, stretch=False)
        self.preview_tree.tag_configure("ok", foreground="#137333")
        self.preview_tree.tag_configure("bad", foreground="#b00020")

        vs = ttk.Scrollbar(g_prev, orient="vertical", command=self.preview_tree.yview)
        hs = ttk.Scrollbar(g_prev, orient="horizontal", command=self.preview_tree.xview)
        self.preview_tree.configure(yscrollcommand=vs.set, xscrollcommand=hs.set)
        self.preview_tree.grid(row=0, column=0, sticky="nsew")
        vs.grid(row=0, column=1, sticky="ns")
        hs.grid(row=1, column=0, sticky="ew")
        g_prev.rowconfigure(0, weight=1)
        g_prev.columnconfigure(0, weight=1)

        # Лог
        g_log = ttk.LabelFrame(parent, text="Лог", padding=6)
        g_log.pack(fill="both", expand=True, padx=8, pady=(4, 8))
        self.log_text = tk.Text(g_log, height=12, wrap="word", state="disabled",
                                background="#1e1e1e", foreground="#d4d4d4", insertbackground="#d4d4d4")
        ls = ttk.Scrollbar(g_log, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=ls.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        ls.pack(side="right", fill="y")

    def _path_row(self, parent, row, label, var, is_file=False, status_var=None):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=4)
        entry = ttk.Entry(parent, textvariable=var)
        entry.grid(row=row, column=1, sticky="ew", pady=4, padx=(6, 0))
        cmd = (lambda: self._browse_file(var)) if is_file else (lambda: self._browse_dir(var))
        ttk.Button(parent, text="Обзор…", command=cmd).grid(row=row, column=2, padx=(6, 0))
        if status_var is not None:
            ttk.Label(parent, textvariable=status_var, foreground="#b00020").grid(
                row=row, column=3, sticky="w", padx=(6, 0))
        return entry

    # ---------- источники ----------
    def _refresh_source_tree(self, tree):
        tree.delete(*tree.get_children())
        for s in tree.sources:
            tree.insert("", "end", values=(s.dir, s.name, s.language, "да" if s.default else ""))

    def _add_source(self, tree):
        title = "Добавить озвучку" if tree.kind == "audio" else "Добавить субтитры"
        dlg = SourceDialog(self, title, app=self)
        if dlg.result:
            dlg.result.kind = tree.kind
            tree.sources.append(dlg.result)
            self._refresh_source_tree(tree)

    def _edit_source(self, tree):
        sel = tree.selection()
        if not sel:
            return
        idx = tree.index(sel[0])
        dlg = SourceDialog(self, "Изменить источник", tree.sources[idx], app=self)
        if dlg.result:
            dlg.result.kind = tree.kind
            tree.sources[idx] = dlg.result
            self._refresh_source_tree(tree)

    def _remove_source(self, tree):
        sel = tree.selection()
        if not sel:
            return
        idx = tree.index(sel[0])
        del tree.sources[idx]
        self._refresh_source_tree(tree)

    def _clear_sources(self, tree):
        if not tree.sources:
            return
        label = "озвучки" if tree.kind == "audio" else "субтитров"
        if messagebox.askyesno("MyViCon", f"Очистить весь список источников {label}?"):
            tree.sources.clear()
            self._refresh_source_tree(tree)

    def _clear_dirs(self):
        self.var_video.set("")
        self.var_output.set("")
        self.var_fonts.set("")

    def _default_output_dir(self, video_dir):
        """Папка вывода по умолчанию: <папка видео>\\Merged."""
        return os.path.join(video_dir, "Merged") if video_dir else ""

    def _on_video_changed(self, *_):
        """Обновлять папку вывода при смене папки видео.

        Меняем автоматически, только если текущая папка вывода пустая или была
        выведена из прежней папки видео (<старое видео>\\Merged). Свою (ручную)
        папку вывода не трогаем.
        """
        new_video = self.var_video.get().strip()
        cur_output = self.var_output.get().strip()
        old_default = self._default_output_dir(self._prev_video)
        if not cur_output or cur_output == old_default:
            self.var_output.set(self._default_output_dir(new_video))
        self._prev_video = new_video

    def _update_tool_status(self):
        """Подсветка полей инструментов: красный + пометка, если файл не найден."""
        for var, status_var, entry in (
            (self.var_mkvmerge, self.var_mkvmerge_status, self.entry_mkvmerge),
            (self.var_mkvpropedit, self.var_mkvpropedit_status, self.entry_mkvpropedit),
        ):
            path = var.get().strip()
            ok = bool(path) and os.path.isfile(path)
            status_var.set("" if ok else "⚠ не найден")
            entry.configure(style="TEntry" if ok else "Invalid.TEntry")

    # ---------- обзор путей ----------
    def _browse_dir(self, var):
        d = filedialog.askdirectory(initialdir=var.get() or self.last_dir)
        if d:
            var.set(d)
            self.last_dir = d

    def _browse_file(self, var):
        start = os.path.dirname(var.get()) if var.get() else self.last_dir
        f = filedialog.askopenfilename(initialdir=start)
        if f:
            var.set(f)
            self.last_dir = os.path.dirname(f)

    # ---------- конфиг ----------
    def _load_into_ui(self):
        c = self.config_data
        self.var_mkvmerge.set(c.mkvmerge)
        self.var_mkvpropedit.set(c.mkvpropedit)
        self.var_video.set(c.video_dir)
        self.var_output.set(c.output_dir)
        self.var_fonts.set(c.fonts_dir)
        self.var_regex.set(c.episode_regex)
        self.var_out_tpl.set(c.output_template)
        self.var_title_tpl.set(c.title_template)
        self.audio_tree.sources = list(c.audio_sources)
        self.sub_tree.sources = list(c.sub_sources)
        self._refresh_source_tree(self.audio_tree)
        self._refresh_source_tree(self.sub_tree)
        self._update_tool_status()

    def _collect_config(self):
        c = self.config_data
        c.mkvmerge = self.var_mkvmerge.get().strip()
        c.mkvpropedit = self.var_mkvpropedit.get().strip()
        c.video_dir = self.var_video.get().strip()
        c.output_dir = self.var_output.get().strip()
        c.fonts_dir = self.var_fonts.get().strip()
        c.episode_regex = self.var_regex.get().strip()
        c.output_template = self.var_out_tpl.get().strip() or "{base} [RUS]"
        c.title_template = self.var_title_tpl.get().strip() or "{base}"
        c.last_dir = self.last_dir
        c.audio_sources = list(self.audio_tree.sources)
        c.sub_sources = list(self.sub_tree.sources)
        return c

    def _save_config(self, notify=True):
        try:
            path, fallback = self._collect_config().save()
        except OSError as e:
            messagebox.showerror("MyViCon", f"Не удалось сохранить настройки:\n{e}")
            return
        if fallback and not self._fallback_notified:
            self._fallback_notified = True
            messagebox.showinfo(
                "MyViCon",
                "Нет прав на запись рядом с программой.\n"
                f"Настройки сохранены в:\n{path}",
            )
        if notify:
            self.status_var.set("Настройки сохранены.")

    # ---------- предпросмотр ----------
    def _on_preview(self):
        cfg = self._collect_config()
        plans, warnings = build_plan(cfg)
        self.preview_tree.delete(*self.preview_tree.get_children())
        for w in warnings:
            self._log(w)
        for p in plans:
            ep = f"{p.episode:02d}" if p.episode >= 0 else "??"
            audio = ", ".join(os.path.basename(t.path) if t.path else f"[нет:{t.source_name}]" for t in p.audio) or "—"
            subs = ", ".join(os.path.basename(t.path) if t.path else f"[нет:{t.source_name}]" for t in p.subs) or "—"
            ok = p.ready
            status = "готово" if ok else "пропуск"
            self.preview_tree.insert("", "end",
                                     values=(ep, os.path.basename(p.video), audio, subs, status),
                                     tags=("ok" if ok else "bad",))
        ready = sum(1 for p in plans if p.ready)
        self.status_var.set(f"Найдено серий: {len(plans)}, готово к сборке: {ready}.")

    # ---------- сборка ----------
    def _on_run(self):
        if self.worker and self.worker.is_alive():
            return
        cfg = self._collect_config()

        self._update_tool_status()
        if not cfg.mkvmerge or not os.path.isfile(cfg.mkvmerge):
            messagebox.showwarning(
                "MyViCon",
                "mkvmerge.exe не найден.\n"
                "Укажите корректный путь к mkvmerge.exe в разделе «Инструменты MKVToolNix».",
            )
            return
        if cfg.fonts_dir and (not cfg.mkvpropedit or not os.path.isfile(cfg.mkvpropedit)):
            messagebox.showwarning(
                "MyViCon",
                "Указана папка со шрифтами, но mkvpropedit.exe не найден.\n"
                "Укажите корректный путь к mkvpropedit.exe или очистите папку шрифтов.",
            )
            return
        if not cfg.video_dir or not os.path.isdir(cfg.video_dir):
            messagebox.showwarning("MyViCon", "Укажите папку с оригиналами (видео).")
            return
        if not cfg.output_dir:
            cfg.output_dir = self._default_output_dir(cfg.video_dir)
            self.var_output.set(cfg.output_dir)

        plans, warnings = build_plan(cfg)
        for w in warnings:
            self._log(w)
        ready = [p for p in plans if p.ready]
        if not ready:
            messagebox.showinfo("MyViCon", "Нет серий, готовых к сборке. Проверьте предпросмотр.")
            return
        if not messagebox.askyesno("MyViCon", f"Собрать серий: {len(ready)}?\nВсего найдено: {len(plans)}."):
            return

        self._save_config()
        self._stop = False
        self.btn_run.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.status_var.set("Сборка…")
        self.progress_var.set(0)
        self.progress_label_var.set(f"0/{len(plans)}")

        self.worker = threading.Thread(target=self._worker, args=(cfg, plans), daemon=True)
        self.worker.start()

    def _worker(self, cfg, plans):
        try:
            run_merge(cfg, plans, self._log, should_stop=lambda: self._stop,
                      progress=self._progress)
        except Exception as e:  # noqa: BLE001 — показываем любую ошибку в логе
            self._log(f"КРИТИЧЕСКАЯ ОШИБКА: {e}")
        finally:
            self.log_queue.put(("__done__", None))

    def _progress(self, done, total):
        self.log_queue.put(("progress", (done, total)))

    def _on_stop(self):
        self._stop = True
        self.status_var.set("Останавливаю после текущей серии…")

    # ---------- лог ----------
    def _log(self, line):
        self.log_queue.put(("line", line))

    def _drain_log(self):
        try:
            while True:
                kind, payload = self.log_queue.get_nowait()
                if kind == "__done__":
                    self.btn_run.config(state="normal")
                    self.btn_stop.config(state="disabled")
                    self.status_var.set("Готово.")
                    continue
                if kind == "progress":
                    done, total = payload
                    pct = (done / total * 100) if total else 0
                    self.progress_var.set(pct)
                    self.progress_label_var.set(f"{done}/{total}")
                    self.status_var.set(f"Сборка… {done}/{total}")
                    continue
                self.log_text.config(state="normal")
                self.log_text.insert("end", payload + "\n")
                self.log_text.see("end")
                self.log_text.config(state="disabled")
        except queue.Empty:
            pass
        self.after(100, self._drain_log)

    def _on_close(self):
        self._save_config(notify=False)
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
