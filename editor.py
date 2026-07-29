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
        self.bind("<Control-v>", self._on_paste, add="+")
        self.bind("<Double-Button-1>", self._on_double_click, add="+")

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

    # ---- 序列化 ----
    def to_document(self):
        ops = []
        for kind, value, _index in self.dump("1.0", "end-1c", text=True, tag=True, image=True, mark=False, window=False):
            if kind == "text":
                ops.append({"k": "text", "text": value})
            elif kind == "tagon" and value in self._style_tags:
                ops.append({"k": "tagon", "name": value})
            elif kind == "tagoff" and value in self._style_tags:
                ops.append({"k": "tagoff", "name": value})
            elif kind == "image" and value in self._images:
                ops.append({"k": "image", "id": value})
        used = {op["name"] for op in ops if op["k"] == "tagon"}
        styles = {k: dict(v) for k, v in self._style_tags.items() if k in used}
        used_imgs = {op["id"] for op in ops if op["k"] == "image"}
        images = {
            img_id: {"file": "images/%s.png" % img_id, "width": m["width"], "height": m["height"]}
            for img_id, m in self._images.items() if img_id in used_imgs
        }
        import snote
        return snote.build_document(styles, ops, images)

    def get_image_blobs(self):
        import io
        blobs = {}
        for img_id, m in self._images.items():
            buf = io.BytesIO()
            m["source"].save(buf, format="PNG")
            blobs[img_id] = buf.getvalue()
        return blobs

    def from_document(self, document, image_blobs):
        import io
        from PIL import Image as PILImage

        self._loading = True
        try:
            self.delete("1.0", "end")
        finally:
            self._loading = False
        self._style_tags.clear()
        self._images.clear()
        self._style_counter = 0
        self._image_counter = 0

        max_s = 0
        for tag, style in document.get("styles", {}).items():
            self._style_tags[tag] = dict(style)
            self.tag_configure(tag, **util.style_to_tag_config(style, self.family, self.base_size))
            num = tag[1:] if tag.startswith("s") and tag[1:].isdigit() else "0"
            max_s = max(max_s, int(num))
        self._style_counter = max_s

        max_i = 0
        for img_id, meta in document.get("images", {}).items():
            data = image_blobs.get(img_id)
            if data is None:
                continue
            source = PILImage.open(io.BytesIO(data)).convert("RGBA")
            w, h = meta["width"], meta["height"]
            photo = self._make_photo(source, w, h)
            self._images[img_id] = {"source": source, "photo": photo, "width": w, "height": h}
            num = img_id[3:] if img_id.startswith("img") and img_id[3:].isdigit() else "0"
            max_i = max(max_i, int(num))
        self._image_counter = max_i

        self._loading = True
        try:
            active = set()
            for op in document.get("ops", []):
                k = op["k"]
                if k == "tagon":
                    active.add(op["name"])
                elif k == "tagoff":
                    active.discard(op["name"])
                elif k == "text":
                    start = self.index("end-1c")
                    super().insert("end-1c", op["text"])
                    end = self.index("end-1c")
                    for t in active:
                        if t in self._style_tags:
                            self.tag_add(t, start, end)
                elif k == "image":
                    img_id = op["id"]
                    if img_id in self._images:
                        self.image_create("end-1c", name=img_id, image=self._images[img_id]["photo"])
        finally:
            self._loading = False
        self._current_style = {}

    # ---- 图片 ----
    def _make_photo(self, source, width, height):
        from PIL import Image as PILImage, ImageTk
        resized = source.resize((int(width), int(height)), PILImage.LANCZOS)
        return ImageTk.PhotoImage(resized)

    def insert_image(self, pil_image, max_width=None):
        source = pil_image.copy()
        width, height = source.size
        if max_width and width > max_width:
            height = int(height * (max_width / width))
            width = max_width
        self._image_counter += 1
        img_id = "img%d" % self._image_counter
        photo = self._make_photo(source, width, height)
        self._images[img_id] = {"source": source, "photo": photo, "width": width, "height": height}
        self.image_create("insert", name=img_id, image=photo)
        self._mark_dirty()
        return img_id

    def _index_of_image(self, img_id):
        for kind, value, index in self.dump("1.0", "end", image=True, text=False, tag=False):
            if kind == "image" and value == img_id:
                return index
        return None

    def set_image_size(self, img_id, width, height):
        meta = self._images.get(img_id)
        if not meta:
            return
        meta["photo"] = self._make_photo(meta["source"], width, height)
        meta["width"], meta["height"] = int(width), int(height)
        idx = self._index_of_image(img_id)
        if idx is not None:
            self.image_configure(idx, image=meta["photo"])
        self._mark_dirty()

    def image_display_size(self, img_id):
        meta = self._images.get(img_id)
        if not meta:
            return None
        return meta["width"], meta["height"]

    def image_source(self, img_id):
        meta = self._images.get(img_id)
        return meta["source"] if meta else None

    # ---- 事件 ----
    def _on_paste(self, _event=None):
        img = util.get_clipboard_image()
        if img is None:
            return
        max_width = max(64, self.winfo_width() - 12)
        self.insert_image(img, max_width=max_width)

    def _on_double_click(self, event):
        idx = self.index("@%d,%d" % (event.x, event.y))
        for kind, value, index in self.dump("1.0", "end", image=True, text=False, tag=False):
            if kind == "image" and self.compare(index, "==", idx):
                self.begin_resize(value)
                return "break"

    def begin_resize(self, img_id):
        if self._resizer is not None:
            self._resizer.destroy()
            self._resizer = None
        idx = self._index_of_image(img_id)
        if idx is None:
            return
        bbox = self.bbox(idx)
        if not bbox:
            return
        from image_resizer import ImageResizer
        self._resizer = ImageResizer(self, img_id, bbox)

    def end_resize(self):
        if self._resizer is not None:
            self._resizer.destroy()
            self._resizer = None
