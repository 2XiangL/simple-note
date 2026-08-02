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
        self._pending = False
        self._type_start = None
        self._on_cursor_style = None
        self._loading = False
        self._on_dirty = None
        self._suppress_modified = 0
        self._resizer = None
        self._ime_style = None        # 上次成功同步给输入法的样式
        self._default_family = None   # 惰性解析：命名字体 -> 真实 family
        self._widget_font = (family, base_size, "")  # 控件基础字体，跟随 _current_style
        self.bind("<KeyPress>", self._on_key_press, add="+")
        self.bind("<KeyRelease>", self._on_cursor_move, add="+")
        self.bind("<ButtonRelease-1>", self._on_cursor_move, add="+")
        self.bind("<Control-v>", self._on_paste, add="+")
        # 菜单/程序化粘贴走 <<Paste>> 虚拟事件，同样拦截：先处理剪贴板图片，
        # 文本粘贴则记录光标待晚绑定补打标签（class 绑定插字发生在晚绑定之前）。
        self.bind("<<Paste>>", self._on_paste, add="+")
        self.bind("<Double-Button-1>", self._on_double_click, add="+")
        # 晚绑定：排在默认 "Text" 类绑定（真正插字）之后触发，使 _stamp_typed_range
        # 能在重绘前把 _current_style 套到刚插入的字上，消除打字时的字号/字体闪烁。
        self._late_tag = "RichTextLate_%x" % id(self)
        self.bindtags(self.bindtags() + (self._late_tag,))
        self.bind_class(self._late_tag, "<KeyPress>", self._stamp_typed_range, add="+")
        self.bind_class(self._late_tag, "<<Paste>>", self._stamp_typed_range, add="+")
        self.bind("<FocusIn>", self._on_focus_in, add="+")
        # <<Modified>> 兜底脏标记：Tcl 层 delete/文本粘贴/撤销/剪切/清空全部绕过
        # Python 级 insert() 覆写，只能靠该虚拟事件补标脏。
        self.bind("<<Modified>>", self._on_modified, add="+")

    # ---- dirty 回调 ----
    def set_on_dirty(self, callback):
        self._on_dirty = callback

    def set_on_cursor_style(self, callback):
        self._on_cursor_style = callback

    def _mark_dirty(self):
        if self._loading:
            return
        if self._on_dirty:
            self._on_dirty()

    def _on_modified(self, _event=None):
        # Tk 每次内容变化都置 modified 并触发本事件；必须手动复位否则只触发一次。
        if not self.edit_modified():
            return
        self.edit_modified(False)
        if self._suppress_modified or self._loading:
            return
        self._mark_dirty()

    def _drain_modified(self):
        # <<Modified>> 虚拟事件由 Tk 异步入队，update idletasks 不派发事件队列；
        # 这里在确有未处理 modified 事件时用 update() 排空，仅供 from_document
        # 清栈使用（_on_modified 复位标志后即完成）。
        if self.edit_modified():
            self.tk.call("update")

    def destroy(self):
        # 清理实例级晚绑定标签，避免绑定表泄漏
        try:
            self.unbind_class(self._late_tag)
        except Exception:
            pass
        super().destroy()

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

    def _on_key_press(self, event):
        # 默认 <KeyPress> 类绑定走 Tcl 层 insert，绕过下面的 Python insert()。
        # 这里在打字前记录光标，由排在类绑定之后的晚绑定 _stamp_typed_range 把当前
        # 样式套到刚输入的范围（发生在同一 KeyPress 事件内、重绘之前）。
        if event.char and not (event.state & 0x4):
            self._type_start = self.index("insert")
        else:
            self._type_start = None

    def _on_cursor_move(self, _event=None):
        if not self._pending:
            before = self.index("insert -1c")
            self._current_style = self._style_at(before)
        self._sync_widget_font()
        self._sync_ime_font()
        if self._on_cursor_style:
            self._on_cursor_style(dict(self._current_style))

    def _stamp_typed_range(self, _event=None):
        # 在默认 "Text" 类绑定（真正插字）之后、重绘之前由晚绑定触发：把
        # _current_style 套到刚输入的范围，避免裸字先以基础字号渲染再跳变（Bug 1）。
        if self._type_start is None:
            return
        start = self._type_start
        self._type_start = None
        now = self.index("insert")
        if self.compare(now, ">", start):
            tag = self._get_or_create_tag(self._current_style)
            self.tag_add(tag, start, now)
            self._pending = False
            self._mark_dirty()

    def _sync_widget_font(self):
        # 让控件基础字体跟随 _current_style：空行的插入光标高度由控件字体决定，
        # 这样回车到新空行后光标高度与当前字号一致。正文已逐字打标签，不受影响。
        font = util.style_to_font(self._current_style, self.family, self.base_size)
        if font != self._widget_font:
            self._widget_font = font
            self.configure(font=font)

    def _sync_ime_font(self, _event=None):
        # 把当前样式同步给系统输入法的预编辑/候选窗，使中文输入时的拼音与正文同号。
        # 仅在 _current_style 真正变化时调用 Win32；非 Windows 平台 imefont 为空操作。
        if self._current_style == self._ime_style:
            return
        try:
            import tkinter.font as tkfont

            import imefont
            if self._default_family is None:
                try:
                    self._default_family = tkfont.Font(name=self.family, exists=True).actual()["family"]
                except Exception:
                    self._default_family = self.family
            point = self._current_style.get("size", self.base_size)
            ok = imefont.set_composition_font(
                self, self._default_family, point,
                bold=bool(self._current_style.get("bold")),
                italic=bool(self._current_style.get("italic")),
                strike=bool(self._current_style.get("strike")),
            )
            if ok:
                self._ime_style = dict(self._current_style)
        except Exception:
            pass

    def _on_focus_in(self, _event=None):
        # 切回窗口后输入上下文可能被重置，强制重新同步一次输入法字体
        self._ime_style = None
        self._sync_widget_font()
        self._sync_ime_font()

    # ---- 文本插入（自动套用当前样式）----
    def insert(self, index, chars, *args):
        start = self.index(index)
        super().insert(index, chars, *args)
        if self._loading:
            self._mark_dirty()
            return
        tag = self._get_or_create_tag(self._current_style)
        end = self.index("%s +%dc" % (start, len(chars)))
        self.tag_add(tag, start, end)
        self._pending = False
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
            sel_first = self.index("sel.first")
            sel_last = self.index("sel.last")
            self._apply_delta_range(sel_first, sel_last, delta)
            # 选区样式只作用于选区本身；后续输入沿用周围样式，但去掉本次应用的属性，
            # 这样加粗/斜体/删除线/换颜色后紧随输入的文字不带该效果（Bug 2）。
            surround = self._style_at(self.index("%s -1c" % sel_last))
            self._current_style = util.merge_style(surround, {k: None for k in delta})
            self._pending = True  # 保护该样式不被随后的光标移动覆盖，直到被输入消费
            self._sync_widget_font()
            self._sync_ime_font()
            if self._on_cursor_style:
                self._on_cursor_style(dict(self._current_style))
        else:
            self._current_style = util.merge_style(self._current_style, delta)
            self._pending = True
            self._sync_widget_font()
            self._sync_ime_font()
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
            elif kind == "tagon" and value in self._style_tags and self._style_tags[value]:
                ops.append({"k": "tagon", "name": value})
            elif kind == "tagoff" and value in self._style_tags and self._style_tags[value]:
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
        used = {value for kind, value, _index in self.dump("1.0", "end", image=True, text=False, tag=False) if kind == "image"}
        blobs = {}
        for img_id, m in self._images.items():
            if img_id not in used:
                continue
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
            w = meta.get("width")
            h = meta.get("height")
            data = image_blobs.get(img_id)
            source = None
            if data is not None and w is not None and h is not None:
                try:
                    source = PILImage.open(io.BytesIO(data)).convert("RGBA")
                except Exception:
                    source = None
            if source is None:
                # 缺图/损坏/缺字段：占位符 + 警告（spec §10）
                print("warning: image %s missing or unreadable; using placeholder" % img_id)
                source = self._placeholder_source()
                if w is None or h is None:
                    w, h = source.size
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
                    styled = [t for t in active if t in self._style_tags]
                    for t in styled:
                        self.tag_add(t, start, end)
                    if not styled:
                        # 无样式正文（旧文件）补一个基础样式标签，确保全文逐字有标签，
                        # 这样控件字体随 _current_style 变化时不会污染正文。
                        self.tag_add(self._get_or_create_tag({}), start, end)
                elif k == "image":
                    img_id = op["id"]
                    if img_id in self._images:
                        self.image_create("end-1c", name=img_id, image=self._images[img_id]["photo"])
        finally:
            self._loading = False
        self._current_style = {}
        self._pending = False
        self._sync_widget_font()
        self._sync_ime_font()
        # 排空载入期间积压的 <<Modified>> 虚拟事件（在 _loading 复位后才派发，
        # 否则会把刚载入的文档误标为脏），随后复位 undo 栈与 modified 标志，
        # 保证载入后首次编辑才触发脏回调。
        self._suppress_modified += 1
        try:
            self._drain_modified()
        finally:
            self._suppress_modified -= 1
        self.edit_reset()
        self.edit_modified(False)

    def set_line_spacing(self, px):
        """设置全局行间距（widget 级 spacing1/2/3）。"""
        self.configure(spacing1=px, spacing2=px, spacing3=0)

    # ---- 图片 ----
    def _placeholder_source(self):
        from PIL import Image as PILImage
        return PILImage.new("RGB", (64, 64), (220, 220, 220))

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

    def delete_image(self, img_id):
        idx = self._index_of_image(img_id)
        if idx is None:
            return
        self.delete(idx)
        self._images.pop(img_id, None)
        self._mark_dirty()

    # ---- 事件 ----
    def _on_paste(self, _event=None):
        img = util.get_clipboard_image()
        if img is not None:
            max_width = max(64, self.winfo_width() - 12)
            self.insert_image(img, max_width=max_width)
            return "break"
        # 文本粘贴：记录位置，待 Tcl 类绑定插入后由晚绑定 _stamp_typed_range 补打标签
        # 有选区时 tk_textPaste 会删选区并从 sel.first 插入，故以 sel.first 为准
        if self.tag_ranges("sel"):
            self._type_start = self.index("sel.first")
        else:
            self._type_start = self.index("insert")

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
