"""SearchDialog：查找对话框（非模态 Toplevel）。"""

import tkinter as tk
from tkinter import ttk

from lang import t


class SearchDialog(tk.Toplevel):
    """当前文档查找：经 editor_provider 回调取活动编辑器，自动跟随文档切换。"""

    def __init__(self, master, editor_provider):
        super().__init__(master)
        self.title(t("查找"))
        self._editor_provider = editor_provider
        self._last_ed = None
        self._build_ui()
        self.bind("<Escape>", lambda e: self._on_close() or "break")
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        bar = ttk.Frame(self, padding=6)
        bar.pack(fill=tk.X)
        self._var = tk.StringVar()
        self._var.trace_add("write", lambda *_: self._on_entry_change())
        self._entry = ttk.Entry(bar, textvariable=self._var, width=24)
        self._entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._entry.bind("<Return>", lambda e: self._find_next())
        self._entry.bind("<Shift-Return>", lambda e: self._find_prev())
        self._entry.bind("<Escape>", lambda e: self._on_close() or "break")
        ttk.Button(bar, text=t("上一个"), width=6, command=self._find_prev).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(bar, text=t("下一个"), width=6, command=self._find_next).pack(side=tk.LEFT, padx=(6, 0))
        self._case_var = tk.BooleanVar(value=False)
        self._case_var.trace_add("write", lambda *_: self._on_entry_change())
        ttk.Checkbutton(bar, text=t("区分大小写"), variable=self._case_var).pack(side=tk.LEFT, padx=6)
        self._status = ttk.Label(bar, text="")
        self._status.pack(side=tk.LEFT, padx=4)

    def focus_entry(self):
        """聚焦输入框并全选，供重开对话框时调用。"""
        self._entry.focus_set()
        self._entry.select_range(0, tk.END)

    def _editor(self):
        return self._editor_provider()

    def _mark_highlighted(self, ed):
        """记录最后高亮的编辑器；切换编辑器时清掉旧编辑器的高亮。"""
        if self._last_ed is not None and self._last_ed is not ed and self._last_ed.winfo_exists():
            self._last_ed.clear_search_highlight()
        self._last_ed = ed

    def _on_entry_change(self):
        ed = self._editor()
        if ed is None or not ed.winfo_exists():
            return
        pattern = self._var.get()
        if not pattern:
            ed.clear_search_highlight()
            self._set_status("")
            return
        case = self._case_var.get()
        n = len(ed.highlight_search(pattern, case, None))
        self._mark_highlighted(ed)
        self._set_status(t("共 %d 处") % n if n else t("无匹配"))

    def _find_next(self):
        self._step(lambda ed, p, c: ed.search_next(p, c))

    def _find_prev(self):
        self._step(lambda ed, p, c: ed.search_prev(p, c))

    def _step(self, fn):
        ed = self._editor()
        if ed is None or not ed.winfo_exists():
            return
        pattern = self._var.get()
        if not pattern:
            self._set_status("")
            return
        result = fn(ed, pattern, self._case_var.get())
        if result:
            self._mark_highlighted(ed)
            self._set_status("%d/%d" % result)
        else:
            self._set_status(t("无匹配"))

    def _set_status(self, text):
        self._status.configure(text=text)

    def refresh(self):
        """按当前编辑器重新计算状态与高亮（文档切换时由 app 调用）。"""
        self._on_entry_change()

    def _on_close(self):
        if self._last_ed is not None and self._last_ed.winfo_exists():
            self._last_ed.clear_search_highlight()
        self._last_ed = None
        self.destroy()
