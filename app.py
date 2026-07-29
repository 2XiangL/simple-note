"""NoteApp：主窗口、菜单、多文档协调。"""

import os
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

import snote
from editor import RichTextEditor
from notes_panel import NotesPanel
from toolbar import FormatToolbar

NOTE_FILTER = [("Simple Note", "*.snote"), ("所有文件", "*.*")]


class NoteDocument:
    def __init__(self, editor, path=None, title=None):
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
        self.root.geometry("900x600")
        self.docs = []
        self.active = None

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

        self.root.protocol("WM_DELETE_WINDOW", self.on_exit)
        self.new_doc()

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
        file_menu.add_command(label="退出", command=self.on_exit)
        menubar.add_cascade(label="文件", menu=file_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="关于程序", command=self.about)
        menubar.add_cascade(label="关于", menu=help_menu)
        self.root.configure(menu=menubar)

        self.root.bind("<Control-n>", lambda e: self.new_doc())
        self.root.bind("<Control-o>", lambda e: self.open_doc())
        self.root.bind("<Control-s>", lambda e: self.save(self.active))

    # ---- 文档生命周期 ----
    def _make_doc(self, path=None, title=None, document=None, blobs=None):
        editor = RichTextEditor(self.editor_host)
        doc = NoteDocument(editor, path=path, title=title)
        editor.set_on_dirty(lambda d=doc: self._on_dirty(d))
        if document is not None:
            editor.from_document(document, blobs or {})
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
        try:
            document, blobs = snote.load_document(path)
        except ValueError as exc:
            messagebox.showerror("打开失败", "无法打开该文件：%s" % exc)
            return
        title = os.path.basename(path)
        doc = self._make_doc(path=path, title=title, document=document, blobs=blobs)
        doc.dirty = False
        self.add_doc(doc)

    def save(self, doc):
        if doc is None:
            return
        if not doc.path:
            self.save_as(doc)
            return
        try:
            document = doc.editor.to_document()
            blobs = doc.editor.get_image_blobs()
            snote.save_document(doc.path, document, blobs)
        except OSError as exc:
            messagebox.showerror("保存失败", "写入失败：%s" % exc)
            return
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
        doc.path = path
        doc.title = os.path.basename(path)
        self.save(doc)

    def close_doc(self, doc):
        if doc is None:
            return
        if doc.dirty and not self._confirm_save(doc):
            return
        doc.editor.end_resize()
        doc.editor.destroy()
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
            self.active.editor.pack_forget()
        self.active = doc
        doc.editor.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        doc.editor.focus_set()
        self.toolbar.set_editor(doc.editor)
        self.panel.select(doc)

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

    def on_exit(self):
        for doc in list(self.docs):
            if doc.dirty:
                self.switch_to(doc)
                if not self._confirm_save(doc):
                    return
        self.root.destroy()

    def about(self):
        messagebox.showinfo("关于 Simple Note", "Simple Note\n轻量化本地便签工具\nTkinter + Pillow")
