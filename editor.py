"""RichTextEditor：tk.Text 子类，复合标签富文本。"""

import tkinter as tk

import util

_NO_SEG = object()  # _apply_delta_range 分段处理的哨兵：当前无打开的段


class RichTextEditor(tk.Text):
    def __init__(self, master=None, family=util.DEFAULT_FAMILY, base_size=util.DEFAULT_SIZE, **kwargs):
        kwargs.setdefault("font", (family, base_size, ""))
        kwargs.setdefault("wrap", "word")
        kwargs.setdefault("undo", True)
        super().__init__(master, **kwargs)
        self.family = family
        self.base_size = base_size
        self._style_tags = {}        # tag id -> style dict
        self._style_tag_lookup = {}  # 样式键(_style_key(style)) -> tag id，O(1) 反查；
                                     # 所有 _style_tags 写点必须同步本表（见 _get_or_create_tag 与 from_document）
        self._images = {}            # img id -> {source, photo, width, height}
        self._image_encoded = {}     # img id -> PNG bytes（源图编码缓存）
        self._style_counter = 0
        self._image_counter = 0
        self._current_style = {}
        self._pending = False
        self._type_start = None
        self._on_cursor_style = None
        self._loading = False
        self._on_dirty = None
        self._resizer = None
        self._ime_style = None        # 上次成功同步给输入法的样式
        self._default_family = None   # 惰性解析：命名字体 -> 真实 family
        self._widget_font = (family, base_size, "")  # 控件基础字体，跟随 _current_style
        self.tag_configure("search_all", background="#fff3b0")  # 全部匹配底纹
        self.tag_configure("search_cur", background="#ffd24d")  # 当前匹配底纹
        self.bind("<KeyPress>", self._on_key_press, add="+")
        self.bind("<KeyRelease>", self._on_cursor_move, add="+")
        self.bind("<ButtonRelease-1>", self._on_cursor_move, add="+")
        self.bind("<Control-v>", self._on_paste, add="+")
        # 依赖 Tk 8.6 语义：Ctrl+V 不合成 <<Paste>>，双绑定才安全；升级 Tk 9 后
        # Ctrl+V 会自动合成粘贴虚拟事件，_on_paste 会跑两次（二次插入=双份粘贴），需防重入。
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
        if self._loading:
            return
        self._mark_dirty()

    def destroy(self):
        # 清理实例级晚绑定标签，避免绑定表泄漏
        try:
            self.unbind_class(self._late_tag)
        except Exception:
            pass
        super().destroy()

    # ---- 样式标签管理 ----
    @staticmethod
    def _style_key(style):
        """样式 dict → 规范 key（键为 str 且唯一，值恒为 str/bool/int/None 浅值）。"""
        return tuple(sorted(style.items()))

    def _get_or_create_tag(self, style):
        # O(1) 反查：样式（dict 相等）即同标签，键为排序后的 items 元组；
        # 样式值恒为 str/bool/int/None 浅值，嵌套排序安全。
        key = self._style_key(style)
        tag = self._style_tag_lookup.get(key)
        if tag is not None:
            return tag
        self._style_counter += 1
        tag = "s%d" % self._style_counter
        self._style_tags[tag] = dict(style)
        self._style_tag_lookup[key] = tag
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
        # 已知限制：event.state & 0x4（Ctrl 位）启发式在需 AltGr 的布局（如德语
        # QWERTZ，AltGr 组合键同样置位 Ctrl 位）下会漏打标签；本机为中文美式键盘
        # 布局（LCID 00000804）无需 AltGr，暂不改逻辑，改需真实 AltGr 布局验证。
        if event.char and not (event.state & 0x4):
            self._type_start = self.index("insert")
        else:
            self._type_start = None

    def _on_cursor_move(self, _event=None, style_index=None):
        # style_index：非 None 时直接从该索引取续写样式（查找跳转用，光标落在
        # 匹配起点，续写样式取匹配文本自身而非其前一字符）
        if not self._pending:
            if style_index is not None:
                self._current_style = self._style_at(style_index)
            else:
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

    # ---- 查找 ----
    def find_matches(self, pattern, case):
        """收集全部匹配 [(start, end)]；case=True 区分大小写；空 pattern 返回 []。"""
        if not pattern:
            return []
        matches = []
        pos = "1.0"
        while True:
            pos = self.search(pattern, pos, stopindex=tk.END, nocase=not case)
            if not pos:
                return matches
            # +Nc 计数依赖 Tk 归一化为整字符（同 insert() 处理 emoji 的算法），勿改成字符计数
            end = self.index("%s+%dc" % (pos, len(pattern)))
            matches.append((pos, end))
            pos = end

    def search_next(self, pattern, case):
        """从选区尾（无选区则 insert）向后环绕查找；命中返回 (序号, 总数)，否则 None。"""
        if not pattern:
            self.clear_search_highlight()
            return None
        origin = "sel.last" if self.tag_ranges("sel") else "insert"
        pos = self.search(pattern, origin, stopindex=tk.END, nocase=not case)
        if not pos:
            pos = self.search(pattern, "1.0", stopindex=tk.END, nocase=not case)
        if not pos:
            self.clear_search_highlight()
            return None
        return self._select_match(pos, pattern, case)

    def search_prev(self, pattern, case):
        """从选区头（无选区则 insert）向前环绕查找；命中返回 (序号, 总数)，否则 None。"""
        if not pattern:
            self.clear_search_highlight()
            return None
        origin = "sel.first" if self.tag_ranges("sel") else "insert"
        pos = self.search(pattern, origin, stopindex="1.0", backwards=True, nocase=not case)
        if not pos:
            pos = self.search(pattern, tk.END, stopindex="1.0", backwards=True, nocase=not case)
        if not pos:
            self.clear_search_highlight()
            return None
        return self._select_match(pos, pattern, case)

    def _select_match(self, start, pattern, case):
        end = self.index("%s+%dc" % (start, len(pattern)))
        self.mark_set("insert", start)
        self.tag_remove("sel", "1.0", tk.END)
        self.tag_add("sel", start, end)
        self.see(start)
        matches = self.highlight_search(pattern, case, start)
        current = 0
        for i, (s, _e) in enumerate(matches):
            if self.compare(s, "==", start):
                current = i + 1
                break
        self._on_cursor_move(style_index=start)  # 跳转后同步 _current_style（续写样式/工具栏/IME）
        return (current, len(matches))

    def highlight_search(self, pattern, case, current_start=None):
        """刷新查找底纹：search_all 覆盖全部匹配，search_cur 覆盖当前匹配；返回匹配列表。"""
        self.tag_remove("search_all", "1.0", tk.END)
        self.tag_remove("search_cur", "1.0", tk.END)
        matches = self.find_matches(pattern, case)
        for s, e in matches:
            self.tag_add("search_all", s, e)
        if current_start is not None:
            self.tag_add("search_cur", current_start, "%s+%dc" % (current_start, len(pattern)))
        self.tag_raise("search_all")
        self.tag_raise("search_cur")  # 后 raise 优先级更高：当前匹配盖住全部匹配
        return matches

    def clear_search_highlight(self):
        """移除全部查找底纹。"""
        self.tag_remove("search_all", "1.0", tk.END)
        self.tag_remove("search_cur", "1.0", tk.END)

    # ---- 文本插入（自动套用当前样式）----
    def insert(self, index, chars, *args):
        start = self.index(index)
        mark_before = self.index("insert")  # 快照插入前光标位置
        super().insert(index, chars, *args)
        if self._loading:
            self._mark_dirty()
            return
        if not chars:
            # 空串插入不移动 insert mark（end 可能 > start 且与插入无关），
            # 整体 no-op，防止把「start→光标」区间误套当前样式（回归守卫）。
            return
        tag = self._get_or_create_tag(self._current_style)
        if mark_before == start:
            # 插入点即光标：Tk 把光标移到插入文本末尾，用 insert mark 作 end，
            # emoji 等按多单位计数的增补字符尾部也不会漏打标签。
            end = self.index("insert")
        else:
            # 光标前插入时 Tk 会把光标按插入长度向后偏移（越过刚插入的文本），
            # 光标后插入时不动光标——两种情况 insert mark 都不能作 end，
            # 一律按码点回退计数（旧行为，对光标前插入正确）。
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
        # 按同样式段批量打标：一次 dump 拉取范围内全部事件，每段只做常数次
        # Tcl 往返（段末 compare + 至多 tag_remove/tag_add 各一次）；段样式
        # 合并 delta 后不变则整段跳过，不新建标签。段边界一律用 dump 返回的
        # Tk 索引（emoji 等按 Tk 单位计数），与逐字实现语义一致。
        events = self.dump(start, end, text=True, tag=True, image=True, mark=False, window=False)
        active = set()
        # dump 不报告「范围起点已激活、范围终点仍激活」的标签（如整段同一
        # 标签时起点无 tagon、终点无 tagoff），需用起点位置的标签播种活跃集合。
        for t in self.tag_names(start):
            if t in self._style_tags:
                active.add(t)
                # 正确性依赖「起点至多一个样式标签」不变量：播种只取第一个样式
                # 标签，一旦该不变量被破坏（同一字符多个样式标签），此处 break
                # 会丢弃其余标签，与下方 next(iter(active)) 的取法同源。
                break
        seg_start = start
        seg_tag = _NO_SEG  # 当前段样式标签；None 表示段已打开但无样式标签

        def close_seg(until):
            nonlocal seg_start, seg_tag
            if seg_tag is _NO_SEG:
                seg_start = until
                return
            if self.compare(until, "<=", seg_start):
                # 状态机里最不显然的一处：该守卫同时处理两类边界——(a) 同索引
                # 重入（内容循环里的二次 close_seg，until 与 seg_start 相等）；
                # (b) 空段保护（tagon/tagoff 紧邻时的空段不产生任何 Tcl 调用）。
                # 勿删：删除后重入/空段会退化为越界 tag 操作。
                seg_start = until
                seg_tag = _NO_SEG
                return
            seg_style = self._style_tags.get(seg_tag) or {}
            new_style = util.merge_style(seg_style, delta)
            if new_style != seg_style:
                new_tag = self._get_or_create_tag(new_style)
                if seg_tag is not None:
                    self.tag_remove(seg_tag, seg_start, until)
                self.tag_add(new_tag, seg_start, until)
            seg_start = until
            seg_tag = _NO_SEG

        i = 0
        n = len(events)
        while i < n:
            index = events[i][2]
            offs, ons, contents = [], [], 0
            while i < n and events[i][2] == index:
                kind, value, _ = events[i]
                if kind == "tagoff" and value in self._style_tags:
                    offs.append(value)
                elif kind == "tagon" and value in self._style_tags:
                    ons.append(value)
                elif kind in ("text", "image"):
                    contents += 1
                i += 1
            # 先按同索引的全部样式标签事件更新活跃集合（顺序无关：一字符一标签
            # 不变量保证同索引至多一个 off 一个 on），再处理紧随的内容事件。
            # 非样式标签（sel 等系统标签）不打断分段，是本门控存在的原因：
            # offs/ons 仅当样式标签切换时非空，才会 close_seg 并推进分段。
            # 勿当作平凡优化删除——删掉后非样式标签的 tagon/tagoff 会误触
            # close_seg(index)，把分段打成碎片。
            if offs or ons:
                close_seg(index)
                for t in offs:
                    active.discard(t)
                for t in ons:
                    active.add(t)
            for _ in range(contents):
                # 死路径防御：实测 dump 会把同标签的连续文本合并为单个 text 事件，
                # 图片与文本索引互斥，故同索引内容事件恒 ≤1（contents 至多 1）；
                # 且样式标签事件已在上面先行处理。此分支勿误读为「支持同索引
                # 多内容事件」——若未来 dump 行为变化，这里不保证多事件正确性。
                tag = next(iter(active), None)
                # 依赖「一字符一标签」不变量：active 至多 1 个样式标签，直接取
                # 第一个即当前段标签；若未来破坏该不变量（同一字符多个样式
                # 标签），此处的取法行为不确定。
                if tag != seg_tag:
                    close_seg(index)
                    seg_start = index
                    seg_tag = tag
        close_seg(end)
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
            cached = self._image_encoded.get(img_id)
            if cached is not None:
                blobs[img_id] = cached
                continue
            buf = io.BytesIO()
            m["source"].save(buf, format="PNG")
            cached = buf.getvalue()
            self._image_encoded[img_id] = cached
            blobs[img_id] = cached
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
        self._style_tag_lookup.clear()
        self._images.clear()
        self._image_encoded.clear()
        self._style_counter = 0
        self._image_counter = 0

        max_s = 0
        for tag, style in document.get("styles", {}).items():
            self._style_tags[tag] = dict(style)
            self._style_tag_lookup[self._style_key(style)] = tag
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
            # 编码缓存留待首次 get_image_blobs 时生成（载入不做无用功）
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
        # 复位 undo 栈与 modified 标志：载入期间积压的 <<Modified>> 事件稍后派发时
        # 标志已是 False，_on_modified 会早退，不会把刚载入的文档误标为脏；
        # 载入后首次编辑（0→1）仍正常触发。
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
        self._image_encoded.pop(img_id, None)
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
        # 局部 dump：只判断点击位置这一个字符是否为图片（图片占单个 Tk 字符位），
        # 免去全文扫描；命中时 dump 返回的 value 即 img_id。与全文版本语义一致：
        # 均为「@x,y 命中图片字符位」才进入缩放。
        for kind, value, _index in self.dump(idx, "%s +1c" % idx, image=True, text=False, tag=False):
            if kind == "image":
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
