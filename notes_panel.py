"""NotesPanel：左侧笔记列表 + 右键菜单。"""

import tkinter as tk
from tkinter import ttk

from lang import t


class NotesPanel(ttk.Frame):
    def __init__(self, master=None, on_switch=None, on_save=None, on_save_as=None, on_close=None):
        super().__init__(master, takefocus=True)
        self.on_switch = on_switch
        self.on_save = on_save
        self.on_save_as = on_save_as
        self.on_close = on_close
        self._docs = []          # 与 listbox 一一对应

        self.listbox = tk.Listbox(self, activestyle="dotbox")
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.listbox.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.listbox.configure(yscrollcommand=sb.set)

        self.listbox.bind("<<ListboxSelect>>", self._on_select)
        self.listbox.bind("<Button-3>", self._on_right_click)

        self.menu = tk.Menu(self, tearoff=0)
        self.menu.add_command(label=t("保存"), command=self._menu_save)
        self.menu.add_command(label=t("另存为"), command=self._menu_save_as)
        self.menu.add_separator()
        self.menu.add_command(label=t("关闭"), command=self._menu_close)

    def add(self, doc):
        self._docs.append(doc)
        self.listbox.insert(tk.END, doc.display_title)
        self.select(doc)

    def remove(self, doc):
        try:
            idx = self._docs.index(doc)
        except ValueError:
            return
        was_selected = idx in self.listbox.curselection()
        self._docs.pop(idx)
        self.listbox.delete(idx)
        # 仅当被移除行原是选中行时才重选首行；移除未选中行时 Tk 的
        # 单选 selection 会跟随索引，保持原选中项不变。
        if was_selected and self._docs:
            self.select(self._docs[0])

    def refresh(self, doc):
        try:
            idx = self._docs.index(doc)
        except ValueError:
            return
        was_selected = idx in self.listbox.curselection()
        was_active = self.listbox.index("active") == idx
        self.listbox.delete(idx)
        self.listbox.insert(idx, doc.display_title)
        if was_selected:
            self.listbox.selection_set(idx)
        if was_active:
            self.listbox.activate(idx)
        self.listbox.see(idx)

    def select(self, doc):
        try:
            idx = self._docs.index(doc)
        except ValueError:
            return
        self.listbox.selection_clear(0, tk.END)
        self.listbox.selection_set(idx)
        self.listbox.activate(idx)
        self.listbox.see(idx)

    def selected_doc(self):
        sel = self.listbox.curselection()
        if not sel:
            return None
        return self._docs[sel[0]]

    def _on_select(self, _event):
        doc = self.selected_doc()
        if doc and self.on_switch:
            self.on_switch(doc)

    def _on_right_click(self, event):
        idx = self.listbox.nearest(event.y)
        if idx < 0 or idx >= len(self._docs):
            return
        self.listbox.selection_clear(0, tk.END)
        self.listbox.selection_set(idx)
        self.menu.tk_popup(event.x_root, event.y_root)

    def _menu_save(self):
        doc = self.selected_doc()
        if doc and self.on_save:
            self.on_save(doc)

    def _menu_save_as(self):
        doc = self.selected_doc()
        if doc and self.on_save_as:
            self.on_save_as(doc)

    def _menu_close(self):
        doc = self.selected_doc()
        if doc and self.on_close:
            self.on_close(doc)
