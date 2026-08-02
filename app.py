"""NoteApp：主窗口、菜单、多文档协调。"""

import os
import sys
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import snote
import settings
import notify
from editor import RichTextEditor
from reminder import ReminderScheduler
from reminder_dialog import ReminderDialog
from tray import TrayController
from notes_panel import NotesPanel
from toolbar import FormatToolbar
from search_dialog import SearchDialog

NOTE_FILTER = [("Simple Note", "*.snote"), ("所有文件", "*.*")]


class NoteDocument:
    def __init__(self, frame, editor, path=None, title=None):
        self.frame = frame
        self.editor = editor
        self.path = path
        self.title = title or (Path(path).name if path else "新建笔记")
        self.dirty = False

    def mark_dirty(self):
        was = self.dirty
        self.dirty = True
        return not was

    @property
    def display_title(self):
        return ("*" if self.dirty else "") + self.title


class NoteApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Simple Note")
        self._title_cache = None
        self.root.geometry("900x600")
        self.docs = []
        self.active = None

        self.settings = settings.load_settings()
        self._line_spacing = self.settings.get("line_spacing", settings.DEFAULT_LINE_SPACING)
        self._ls_var = tk.StringVar(value=self._line_spacing)

        self.scheduler = ReminderScheduler()
        self.scheduler.load_dict(self.settings.get("pomodoro"), self.settings.get("reminders"))
        self._sound_cfg = self.settings.get("sound") or dict(settings.DEFAULT_SOUND)
        self._reminder_dlg = None
        self._search_dlg = None
        self.scheduler.arm(datetime.now())

        self._build_menu()
        self.toolbar = FormatToolbar(root)
        self.toolbar.pack(side=tk.TOP, fill=tk.X)
        self.body = tk.PanedWindow(root, orient=tk.HORIZONTAL)
        self.body.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self.panel = NotesPanel(
            self.body,
            on_switch=self.switch_to,
            on_save=lambda d: self.save(d),
            on_save_as=lambda d: self.save_as(d),
            on_close=lambda d: self.close_doc(d),
        )
        self.body.add(self.panel, minsize=150, width=180)

        self.editor_host = tk.Frame(self.body)
        self.body.add(self.editor_host, minsize=300)

        self.new_doc()
        self.tray = TrayController(
            self.root,
            on_quit=self._real_quit,
            on_hide=lambda: self.active is not None and self.active.editor.end_resize(),
        )
        self.tray.start()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._tick()

    # ---- 菜单 ----
    def _build_menu(self):
        menubar = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="新建", command=self.new_doc, accelerator="Ctrl+N")
        file_menu.add_command(label="打开", command=self.open_doc, accelerator="Ctrl+O")
        file_menu.add_separator()
        file_menu.add_command(label="保存", command=lambda: self.save(self.active), accelerator="Ctrl+S")
        file_menu.add_command(label="另存为", command=lambda: self.save_as(self.active))
        file_menu.add_separator()
        file_menu.add_command(label="退出", command=self._real_quit)
        menubar.add_cascade(label="文件", menu=file_menu)

        edit_menu = tk.Menu(menubar, tearoff=0)
        edit_menu.add_command(label="查找...", command=self._open_search_dialog, accelerator="Ctrl+F")
        menubar.add_cascade(label="编辑", menu=edit_menu)

        view_menu = tk.Menu(menubar, tearoff=0)
        for name in settings.PRESET_ORDER:
            view_menu.add_radiobutton(
                label=name, value=name, variable=self._ls_var, command=self._on_line_spacing
            )
        menubar.add_cascade(label="查看", menu=view_menu)

        remind_menu = tk.Menu(menubar, tearoff=0)
        remind_menu.add_command(label="管理提醒...", command=self._open_reminder_dialog)
        remind_menu.add_separator()
        remind_menu.add_command(label="开始番茄钟", command=self._start_pomodoro)
        remind_menu.add_command(label="停止番茄钟", command=self._stop_pomodoro)
        menubar.add_cascade(label="提醒", menu=remind_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="关于程序", command=self.about)
        menubar.add_cascade(label="关于", menu=help_menu)
        self.root.configure(menu=menubar)

        self.root.bind("<Control-n>", lambda e: self.new_doc())
        self.root.bind("<Control-o>", lambda e: self.open_doc())
        self.root.bind("<Control-s>", lambda e: self.save(self.active))
        self.root.bind("<Control-f>", lambda e: self._open_search_dialog())

    def _on_line_spacing(self):
        level = self._ls_var.get()
        self._line_spacing = level
        px = settings.px_for_level(level)
        for doc in self.docs:
            doc.editor.set_line_spacing(px)
        self.settings["line_spacing"] = level
        settings.save_settings(self.settings)

    # ---- 提醒 ----
    def _tick(self):
        try:
            now = datetime.now()
            events = self.scheduler.tick(now)
            if events:
                title, msg = notify.format_events(events)
                try:
                    notify.notify(self.root, title, msg, self._sound_cfg)
                except Exception as exc:
                    print("warning: reminder notify error: %s" % exc, file=sys.stderr)
            # 仅一次性提醒到期会改变持久化状态（fired 条目被移除）；
            # 番茄钟 phase 与每日提醒触发不序列化，无需写盘。
            if any(ev["kind"] == "oneshot" for ev in events):
                self._persist()
            self._refresh_title(now)
            if self._reminder_dlg is not None and self._reminder_dlg.winfo_exists():
                if events:
                    self._reminder_dlg.refresh_list()
                else:
                    self._reminder_dlg.refresh_status()
        except Exception as exc:
            print("warning: reminder tick error: %s" % exc, file=sys.stderr)
        finally:
            self.root.after(1000, self._tick)

    def _refresh_title(self, now=None):
        rem = self.scheduler.pomodoro_remaining(now)
        title = "Simple Note" if rem is None else "Simple Note — %s %s（%s）" % rem
        if title != self._title_cache:
            self._title_cache = title
            self.root.title(title)

    def _persist(self):
        pomodoro, reminders = self.scheduler.to_dict()
        self.settings["pomodoro"] = pomodoro
        self.settings["reminders"] = reminders
        if self._reminder_dlg is not None and self._reminder_dlg.winfo_exists():
            self._sound_cfg = self._reminder_dlg.sound_config()
        self.settings["sound"] = self._sound_cfg
        settings.save_settings(self.settings)

    def _on_reminder_change(self):
        self._persist()
        self._refresh_title()

    def _open_reminder_dialog(self):
        if self._reminder_dlg is not None and self._reminder_dlg.winfo_exists():
            self._reminder_dlg.lift()
            return
        self._reminder_dlg = ReminderDialog(
            self.root, self.scheduler, self._sound_cfg, on_change=self._on_reminder_change
        )

    def _open_search_dialog(self):
        if getattr(self, "_search_dlg", None) is not None and self._search_dlg.winfo_exists():
            self._search_dlg.lift()
            self._search_dlg.focus_entry()
            return
        self._search_dlg = SearchDialog(
            self.root, lambda: self.active.editor if self.active is not None else None
        )
        self._search_dlg.focus_entry()

    def _start_pomodoro(self):
        if self.scheduler.pomodoro_phase() != "idle":
            return
        self.scheduler.start_pomodoro(datetime.now())
        self._refresh_title()

    def _stop_pomodoro(self):
        self.scheduler.stop_pomodoro()
        self._refresh_title()

    # ---- 文档生命周期 ----
    def _make_doc(self, path=None, title=None, document=None, blobs=None):
        frame = tk.Frame(self.editor_host)
        editor = RichTextEditor(frame)
        sb = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=editor.yview)
        editor.configure(yscrollcommand=sb.set)
        editor.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        editor.set_line_spacing(settings.px_for_level(self._line_spacing))
        doc = NoteDocument(frame, editor, path=path, title=title)
        editor.set_on_dirty(lambda d=doc: self._on_dirty(d))
        if document is not None:
            try:
                editor.from_document(document, blobs or {})
            except Exception:
                editor.destroy()  # 先销毁子控件再销毁容器，保住孤儿控件守卫
                frame.destroy()
                raise
        return doc

    def add_doc(self, doc):
        self.docs.append(doc)
        self.panel.add(doc)
        self.switch_to(doc)

    def new_doc(self):
        doc = self._make_doc()
        self.add_doc(doc)

    def open_doc(self):
        path = filedialog.askopenfilename(title="打开笔记", filetypes=NOTE_FILTER)
        if not path:
            return
        key = os.path.normcase(os.path.realpath(path))
        for doc in self.docs:
            # 已在打开列表中的文档（doc.path 可能为 None=未保存，需过滤）
            if doc.path is not None and os.path.normcase(os.path.realpath(doc.path)) == key:
                self.switch_to(doc)
                return
        try:
            document, blobs = snote.load_document(path)
        except ValueError as exc:
            messagebox.showerror("打开失败", "无法打开该文件：%s" % exc)
            return
        title = os.path.basename(path)
        try:
            doc = self._make_doc(path=path, title=title, document=document, blobs=blobs)
        except Exception as exc:
            messagebox.showerror("打开失败", "解析笔记内容失败：%s" % exc)
            return
        doc.dirty = False
        self.add_doc(doc)

    def _write_to(self, doc, path):
        try:
            document = doc.editor.to_document()
            blobs = doc.editor.get_image_blobs()
            snote.save_document(path, document, blobs)
            return True
        except Exception as exc:
            # 除磁盘 OSError 外，PIL 编码/Tcl 等异常也走“保存失败”弹框，不裸抛
            messagebox.showerror("保存失败", "写入失败：%s" % exc)
            return False

    def save(self, doc):
        if doc is None:
            return
        if not doc.path:
            self.save_as(doc)
            return
        if self._write_to(doc, doc.path):
            doc.dirty = False
            self.panel.refresh(doc)

    def save_as(self, doc):
        if doc is None:
            return
        path = filedialog.asksaveasfilename(
            title="另存为", defaultextension=".snote", filetypes=NOTE_FILTER
        )
        if not path:
            return
        if self._write_to(doc, path):
            doc.path = path
            doc.title = os.path.basename(path)
            doc.dirty = False
            self.panel.refresh(doc)

    def close_doc(self, doc):
        if doc is None:
            return
        if doc.dirty and not self._confirm_save(doc):
            return
        doc.editor.end_resize()
        doc.frame.destroy()
        idx = self.docs.index(doc)
        self.docs.remove(doc)
        self.panel.remove(doc)
        if not self.docs:
            self.new_doc()
            return
        if self.active is doc:
            nxt = self.docs[min(idx, len(self.docs) - 1)]
            self.switch_to(nxt)

    def switch_to(self, doc):
        if doc is None:
            return
        if self.active is doc:
            return
        if self.active is not None:
            self.active.editor.end_resize()
            self.active.frame.pack_forget()
        self.active = doc
        doc.frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        doc.editor.focus_set()
        self.toolbar.set_editor(doc.editor)
        doc.editor._on_cursor_move()
        self.panel.select(doc)
        if self._search_dlg is not None and self._search_dlg.winfo_exists():
            self._search_dlg.refresh()

    def _on_dirty(self, doc):
        if doc is None:
            return
        if doc.mark_dirty():
            self.panel.refresh(doc)

    # ---- 退出/提示 ----
    def _confirm_save(self, doc):
        ans = messagebox.askyesnocancel(
            "Simple Note", "“%s”未保存，是否保存？" % doc.title
        )
        if ans is None:
            return False
        if ans:
            self.save(doc)
            return not doc.dirty
        return True

    def _on_close(self):
        if self.tray.is_running():
            self.tray.hide()
        else:
            self._real_quit()

    def _real_quit(self):
        for doc in list(self.docs):
            if doc.dirty:
                self.switch_to(doc)
                if not self._confirm_save(doc):
                    return
        if self._reminder_dlg is not None and self._reminder_dlg.winfo_exists():
            self._reminder_dlg._apply_pomodoro_cfg()
        self._persist()
        self.tray.stop()
        self.root.destroy()

    def about(self):
        messagebox.showinfo("关于 Simple Note", "Simple Note\n轻量化本地便签工具\nTkinter + Pillow")
