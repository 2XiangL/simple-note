"""TodoPanel：待办清单面板（视图 + 回调，数据在 app 侧）。"""

import tkinter as tk
from tkinter import messagebox, ttk

from lang import t


class TodoPanel(ttk.Frame):
    def __init__(self, master=None, on_add=None, on_toggle=None, on_remove=None,
                 on_move=None, on_set_current=None, on_toggle_focus=None):
        super().__init__(master)
        self.on_add = on_add
        self.on_toggle = on_toggle
        self.on_remove = on_remove
        self.on_move = on_move
        self.on_set_current = on_set_current
        self.on_toggle_focus = on_toggle_focus
        self._running = False
        self._current_id = None
        self._ids = []  # [(tree iid, todo id)]

        top = ttk.Frame(self)
        top.pack(fill=tk.X, padx=4, pady=2)
        self._entry_var = tk.StringVar()
        ttk.Entry(top, textvariable=self._entry_var).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(top, text=t("添加"), command=self._on_add).pack(side=tk.LEFT, padx=4)

        mid = ttk.Frame(self)
        mid.pack(fill=tk.BOTH, expand=True, padx=4, pady=2)
        self._tree = ttk.Treeview(
            mid, columns=("text",), show="tree headings", selectmode="browse"
        )
        self._tree.heading("#0", text=t("状态"))
        self._tree.heading("text", text=t("内容"))
        self._tree.column("#0", width=52, stretch=False)
        self._tree.column("text", width=120)
        self._tree.pack(fill=tk.BOTH, expand=True)
        self._tree.bind("<Double-1>", self._on_double_click)
        self._tree.bind("<Button-3>", self._on_right_click)

        self._focus_btn = ttk.Button(self, text=t("开始专注"), command=self._on_focus)
        self._focus_btn.pack(fill=tk.X, padx=4, pady=2)

        self.menu = tk.Menu(self, tearoff=0)
        self.menu.add_command(label=t("设为当前任务"), command=self._menu_set_current)
        self.menu.add_command(label=t("取消当前任务"), command=self._menu_clear_current)
        self.menu.add_command(label=t("切换完成"), command=self._menu_toggle)
        self.menu.add_separator()
        self.menu.add_command(label=t("上移"), command=lambda: self._menu_move(-1))
        self.menu.add_command(label=t("下移"), command=lambda: self._menu_move(1))
        self.menu.add_separator()
        self.menu.add_command(label=t("删除"), command=self._menu_remove)

    # ---- 渲染 ----
    def set_items(self, items, current_id, running):
        sel = self._selected_id()
        for iid in self._tree.get_children():
            self._tree.delete(iid)
        self._ids = []
        for e in items:
            mark = ("▶" if e["id"] == current_id else "") + ("☑" if e["done"] else "☐")
            text = e["text"] + (t("（🍅×%d）") % e["pomo"] if e["pomo"] else "")
            iid = self._tree.insert("", tk.END, values=(text,), text=mark)
            self._ids.append((iid, e["id"]))
        self._current_id = current_id
        self._running = running
        self._focus_btn.configure(text=t("停止专注") if running else t("开始专注"))
        if sel is not None:
            self._select_id(sel)

    def _selected_id(self):
        sel = self._tree.selection()
        if not sel:
            return None
        for iid, tid in self._ids:
            if iid == sel[0]:
                return tid
        return None

    def _select_id(self, tid):
        for iid, t_ in self._ids:
            if t_ == tid:
                self._tree.selection_set(iid)
                self._tree.see(iid)
                return

    # ---- 交互 ----
    def _on_add(self):
        text = self._entry_var.get().strip()
        if not text:
            messagebox.showinfo(t("待办"), t("请输入任务内容。"), parent=self)
            return
        if self.on_add:
            self.on_add(text)
        self._entry_var.set("")

    def _on_double_click(self, _event):
        tid = self._selected_id()
        if tid and self.on_toggle:
            self.on_toggle(tid)

    def _on_focus(self):
        if self.on_toggle_focus:
            self.on_toggle_focus()

    def _on_right_click(self, event):
        iid = self._tree.identify_row(event.y)
        if not iid:
            return
        self._tree.selection_set(iid)
        self.menu.tk_popup(event.x_root, event.y_root)

    def _menu_set_current(self):
        tid = self._selected_id()
        if tid and self.on_set_current:
            self.on_set_current(tid)

    def _menu_clear_current(self):
        if self.on_set_current:
            self.on_set_current(None)

    def _menu_toggle(self):
        tid = self._selected_id()
        if tid and self.on_toggle:
            self.on_toggle(tid)

    def _menu_move(self, delta):
        tid = self._selected_id()
        if tid and self.on_move:
            self.on_move(tid, delta)

    def _menu_remove(self):
        tid = self._selected_id()
        if tid and self.on_remove:
            self.on_remove(tid)
