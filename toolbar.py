"""FormatToolbar：颜色/字号/加粗/斜体/删除线。"""

import tkinter as tk
from tkinter import colorchooser, ttk

import util


class FormatToolbar(ttk.Frame):
    def __init__(self, master=None):
        super().__init__(master)
        self.editor = None
        self._build()

    def _build(self):
        self.color_btn = ttk.Button(self, text="颜色", width=6, command=self.on_color)
        self.color_btn.pack(side=tk.LEFT, padx=2, pady=2)

        self.size_var = tk.StringVar(value=str(util.DEFAULT_SIZE))
        self.size_box = ttk.Combobox(
            self, textvariable=self.size_var, width=4, values=[str(s) for s in range(8, 73, 2)]
        )
        self.size_box.bind("<<ComboboxSelected>>", lambda e: self.on_size())
        self.size_box.bind("<Return>", lambda e: self.on_size())
        self.size_box.pack(side=tk.LEFT, padx=2)

        self.bold_btn = ttk.Button(self, text="B", width=3, command=lambda: self.toggle("bold"))
        self.bold_btn.pack(side=tk.LEFT, padx=2)
        self.italic_btn = ttk.Button(self, text="I", width=3, command=lambda: self.toggle("italic"))
        self.italic_btn.pack(side=tk.LEFT, padx=2)
        self.strike_btn = ttk.Button(self, text="S", width=3, command=lambda: self.toggle("strike"))
        self.strike_btn.pack(side=tk.LEFT, padx=2)

    def set_editor(self, editor):
        self.editor = editor
        editor.set_on_cursor_style(self._refresh_size)

    def _refresh_size(self, style):
        # 字号框正在被用户编辑时不覆盖，避免打架
        if self.focus_get() is self.size_box:
            return
        size = style.get("size", util.DEFAULT_SIZE)
        self.size_var.set(str(size))

    def on_color(self):
        if not self.editor:
            return
        _, hexcolor = colorchooser.askcolor(title="选择颜色")
        if hexcolor:
            self.editor.apply_style_to_selection({"fg": hexcolor})

    def on_size(self):
        if not self.editor:
            return
        try:
            size = int(self.size_var.get())
        except ValueError:
            return
        self.editor.apply_style_to_selection({"size": size})

    def toggle(self, attr):
        if not self.editor:
            return
        current = self.editor.effective_style()
        self.editor.apply_style_to_selection({attr: not current.get(attr, False)})
