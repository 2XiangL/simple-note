"""RichTextEditor：tk.Text 子类，复合标签富文本。"""

import tkinter as tk

import util


class RichTextEditor(tk.Text):
    def __init__(self, master=None, family=util.DEFAULT_FAMILY, base_size=util.DEFAULT_SIZE, **kwargs):
        kwargs.setdefault("font", (family, base_size, ""))
        kwargs.setdefault("wrap", "word")
        kwargs.setdefault("undo", True)
        super().__init__(master, **kwargs)
        self.family = family
        self.base_size = base_size
        self._style_tags = {}        # tag id -> style dict
        self._images = {}            # img id -> {source, photo, width, height}
        self._style_counter = 0
        self._image_counter = 0
        self._current_style = {}
        self._loading = False
        self._on_dirty = None
        self._resizer = None
        self.bind("<KeyRelease>", self._on_cursor_move, add="+")
        self.bind("<ButtonRelease-1>", self._on_cursor_move, add="+")

    # ---- dirty 回调 ----
    def set_on_dirty(self, callback):
        self._on_dirty = callback

    def _mark_dirty(self):
        if self._loading:
            return
        if self._on_dirty:
            self._on_dirty()

    # ---- 样式标签管理 ----
    def _get_or_create_tag(self, style):
        for tag, st in self._style_tags.items():
            if st == style:
                return tag
        self._style_counter += 1
        tag = "s%d" % self._style_counter
        self._style_tags[tag] = dict(style)
        self.tag_configure(tag, **util.style_to_tag_config(style, self.family, self.base_size))
        return tag

    def _style_at(self, index):
        for tag in self.tag_names(index):
            if tag in self._style_tags:
                return dict(self._style_tags[tag])
        return {}

    def _on_cursor_move(self, _event=None):
        before = self.index("insert -1c")
        self._current_style = self._style_at(before)

    # ---- 文本插入（自动套用当前样式）----
    def insert(self, index, chars, *args):
        start = self.index(index)
        super().insert(index, chars, *args)
        if self._loading or not self._current_style:
            self._mark_dirty()
            return
        tag = self._get_or_create_tag(self._current_style)
        end = self.index("%s +%dc" % (start, len(chars)))
        self.tag_add(tag, start, end)
        self._mark_dirty()

    def insert_plain(self, text):
        """供测试/加载使用：插入不带样式的纯文本。"""
        self._loading = True
        try:
            self.insert("end-1c", text)
        finally:
            self._loading = False

    # ---- 对选区应用样式 ----
    def effective_style(self):
        if self.tag_ranges("sel"):
            return self._style_at(self.index("sel.first"))
        return dict(self._current_style)

    def apply_style_to_selection(self, delta):
        if self.tag_ranges("sel"):
            self._apply_delta_range(self.index("sel.first"), self.index("sel.last"), delta)
        else:
            self._current_style = util.merge_style(self._current_style, delta)
            self._mark_dirty()

    def _apply_delta_range(self, start, end, delta):
        idx = start
        while self.compare(idx, "<", end):
            current = self._style_at(idx)
            new_style = util.merge_style(current, delta)
            new_tag = self._get_or_create_tag(new_style)
            for t in list(self.tag_names(idx)):
                if t in self._style_tags:
                    self.tag_remove(t, idx, "%s +1c" % idx)
            self.tag_add(new_tag, idx, "%s +1c" % idx)
            idx = self.index("%s +1c" % idx)
        self._on_cursor_move()
        self._mark_dirty()
