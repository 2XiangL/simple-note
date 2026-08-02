import editor
import util


def test_apply_bold_to_range(tk_root):
    ed = editor.RichTextEditor(tk_root)
    ed.insert_plain("hello")
    ed._apply_delta_range("1.0", "1.5", {"bold": True})
    assert ed._style_at("1.0").get("bold") is True
    assert ed._style_at("1.2").get("bold") is True


def test_merge_size_with_bold(tk_root):
    ed = editor.RichTextEditor(tk_root)
    ed.insert_plain("abc")
    ed._apply_delta_range("1.0", "1.3", {"bold": True})
    ed._apply_delta_range("1.0", "1.3", {"size": 20})
    st = ed._style_at("1.1")
    assert st.get("bold") is True
    assert st.get("size") == 20


def test_each_char_one_style_tag(tk_root):
    ed = editor.RichTextEditor(tk_root)
    ed.insert_plain("ab")
    ed._apply_delta_range("1.0", "1.1", {"bold": True})
    ed._apply_delta_range("1.1", "1.2", {"italic": True})
    # 字符 1.0 仅有一个样式标签
    tags0 = [t for t in ed.tag_names("1.0") if t in ed._style_tags]
    tags1 = [t for t in ed.tag_names("1.1") if t in ed._style_tags]
    assert len(tags0) == 1
    assert len(tags1) == 1
    assert tags0 != tags1


def test_apply_delta_range_matches_per_char_semantics(tk_root):
    # 按同样式段批量打标的实现必须与旧逐字符语义等价：范围内每字符的
    # 样式等于 merge(原样式, delta)；逐字仅保留一个样式标签。
    ed = editor.RichTextEditor(tk_root)
    ed.insert_plain("ABCDEFGHIJKLMNOP")  # 16 个普通字符
    ed._apply_delta_range("1.2", "1.4", {"bold": True})     # C、D 加粗
    ed._apply_delta_range("1.5", "1.7", {"italic": True})   # F、G 斜体
    ed._apply_delta_range("1.8", "1.9", {"size": 14})       # I 改字号
    ed._apply_delta_range("1.10", "1.12", {"fg": "#ff0000", "bold": True})  # K、L 红色加粗
    idxs = ["1.%d" % i for i in range(16)]
    before = {i: ed._style_at(i) for i in idxs}
    ed._apply_delta_range("1.0", "1.16", {"strike": True})
    for i in idxs:
        assert ed._style_at(i) == util.merge_style(before[i], {"strike": True}), i
        style_tags = [t for t in ed.tag_names(i) if t in ed._style_tags]
        assert len(style_tags) == 1, "字符 %s 应仅有一个样式标签" % i
    # delta 值为 None 的删除分支同样逐字等价
    ed._apply_delta_range("1.0", "1.16", {"bold": None})
    for i in idxs:
        expected = util.merge_style(util.merge_style(before[i], {"strike": True}), {"bold": None})
        assert ed._style_at(i) == expected, i


def test_apply_delta_range_leaves_outside_range_untouched(tk_root):
    # 范围外的字符：样式标签与样式内容都不得被改动
    ed = editor.RichTextEditor(tk_root)
    ed.insert_plain("abcdef")
    ed._apply_delta_range("1.1", "1.2", {"bold": True})    # b 加粗
    ed._apply_delta_range("1.3", "1.4", {"italic": True})  # d 斜体
    outside = {i: ed.tag_names(i) for i in ("1.0", "1.4", "1.5")}
    ed._apply_delta_range("1.1", "1.4", {"strike": True})  # 只动 b、c、d
    for i, tags in outside.items():
        assert ed.tag_names(i) == tags
    assert ed._style_at("1.0") == {}
    assert ed._style_at("1.1") == {"bold": True, "strike": True}
    assert ed._style_at("1.2") == {"strike": True}
    assert ed._style_at("1.3") == {"italic": True, "strike": True}
    assert ed._style_at("1.4") == {}


def test_apply_delta_range_unchanged_style_no_new_tags(tk_root):
    # 对已全部加粗的内容重复应用 {"bold": True}：样式未变段整段跳过，
    # 不得新建标签（_style_tags 数量不增长），原标签原样保留。
    ed = editor.RichTextEditor(tk_root)
    ed.insert_plain("abc")
    ed._apply_delta_range("1.0", "1.3", {"bold": True})
    n_tags = len(ed._style_tags)
    ed._apply_delta_range("1.0", "1.3", {"bold": True})
    assert len(ed._style_tags) == n_tags
    tags = [t for t in ed.tag_names("1.0") if t in ed._style_tags]
    assert len(tags) == 1
    assert ed._style_tags[tags[0]] == {"bold": True}


def test_apply_delta_range_tags_images_in_segment(tk_root):
    # 图片与文本同列处理：图片随所在段一起换标签（与旧逐字符实现一致）
    from PIL import Image as PILImage
    ed = editor.RichTextEditor(tk_root)
    ed.insert_plain("ab")
    img_id = ed.insert_image(PILImage.new("RGBA", (20, 20), (255, 0, 0, 255)))
    ed.insert_plain("cd")
    img_idx = ed._index_of_image(img_id)
    ed._apply_delta_range("1.0", "%s +1c" % img_idx, {"bold": True})          # ab+图片 加粗
    ed._apply_delta_range(img_idx, "%s +2c" % img_idx, {"italic": True})      # 图片+c 斜体
    assert ed._style_at("1.0") == {"bold": True}
    assert ed._style_at(img_idx) == {"bold": True, "italic": True}
    assert ed._style_at("%s +1c" % img_idx) == {"italic": True}
    assert ed._style_at("%s +2c" % img_idx) == {}
    img_tags = [t for t in ed.tag_names(img_idx) if t in ed._style_tags]
    assert len(img_tags) == 1


def test_apply_delta_range_emoji_uses_tk_indices(tk_root):
    # emoji 在 Tk 索引中占多个单位（本机 Tk 8.6 为 3 个）；段边界必须以
    # dump 返回的 Tk 索引为准，不得按 Python 字符串长度计数。
    ed = editor.RichTextEditor(tk_root)
    ed.insert_plain("A\U0001F600B")
    ed._apply_delta_range("1.3", "1.4", {"bold": True})  # B 位于 Tk 索引 1.3
    assert ed._style_at("1.0") == {}
    assert ed._style_at("1.3") == {"bold": True}
    ed._apply_delta_range("1.0", "1.4", {"strike": True})
    for idx in ("1.0", "1.1", "1.2", "1.3"):
        assert "strike" in ed._style_at(idx), idx
    assert ed._style_at("1.3") == {"bold": True, "strike": True}


def test_insert_inherits_current_style(tk_root):
    ed = editor.RichTextEditor(tk_root)
    ed._current_style = {"bold": True}
    ed.insert("end-1c", "Hi")
    tags = [t for t in ed.tag_names("1.0") if t in ed._style_tags]
    assert len(tags) == 1
    assert ed._style_at("1.0").get("bold") is True


def test_insert_base_text_gets_base_tag(tk_root):
    # 基础样式插入也打一个基础样式标签：让控件字体可随 _current_style 变化
    # 而不污染无标签正文（空行光标修复的前提）。
    ed = editor.RichTextEditor(tk_root)
    ed.insert("end-1c", "Hi")
    tags = [t for t in ed.tag_names("1.0") if t in ed._style_tags]
    assert len(tags) == 1
    assert ed._style_tags[tags[0]] == {}


def test_insert_with_emoji_tags_full_range(tk_root):
    # 程序化 insert 含 emoji 的字符串：end 取 Tk 的 insert mark（已移到插入
    # 末尾），不按 Python 码点计数——emoji 在 Tk 索引中占多单位（本机 2 个、
    # 部分 Tcl 8.6 构建 3 个），按码点计数会少覆盖尾部字符（"A😀B" 码点 3 个、
    # Tk 单位 ≥4 个，旧实现漏打尾部字符标签）。
    ed = editor.RichTextEditor(tk_root)
    ed._current_style = {"bold": True}
    ed.insert("end-1c", "A\U0001F600B")
    n = int(ed.index("end-1c").split(".")[1])  # 插入后内容占用的 Tk 单位数
    for i in range(n):
        assert ed._style_at("1.%d" % i).get("bold") is True, i
    assert ed._style_at("1.%d" % n) == {}


def test_insert_after_cursor_falls_back_to_codepoint_end(tk_root):
    # 光标在文档中部、程序化插入到末尾：Tk 不移动 insert mark，
    # end 回退按码点计数（兼容旧行为，不越界打标）。
    ed = editor.RichTextEditor(tk_root)
    ed.insert_plain("abcde")
    ed.mark_set("insert", "1.2")
    ed._current_style = {"bold": True}
    ed.insert("end-1c", "XY")
    assert ed._style_at("1.5").get("bold") is True
    assert ed._style_at("1.6").get("bold") is True
    assert ed._style_at("1.7") == {}
    assert ed._style_at("1.2") == {}  # 光标前的既有文本未被误标


def test_insert_empty_string_is_noop(tk_root):
    # 空串插入不移动 insert mark：若光标在插入点之后，end=光标位置 > start，
    # 守卫不触发会把「start→光标」整段套上当前样式。空串必须整体 no-op。
    from editor import RichTextEditor
    ed = RichTextEditor(tk_root)
    ed.insert("end", "abc")
    ed.tag_add(ed._get_or_create_tag({"bold": True}), "1.1", "1.4")
    before = [ed._style_at(i) for i in ("1.0", "1.1", "1.2")]
    ed.insert("1.0", "")   # 空串插入，光标在 1.3
    after = [ed._style_at(i) for i in ("1.0", "1.1", "1.2")]
    assert after == before, "空串插入不应改变任何字符的样式"


def test_insert_before_cursor_only_tags_inserted_text(tk_root):
    # 光标前插入：Tk 会把光标按插入长度向后偏移，insert mark 越过了刚插入的
    # 文本——end 必须按码点计数（旧行为），否则 tag_add 会误标插入点之后的
    # 既有文本。仅插入点即光标时才可用 insert mark 作 end（emoji 安全）。
    from editor import RichTextEditor
    ed = RichTextEditor(tk_root)
    ed.insert("end", "abc")                                  # a=1.0 b=1.1 c=1.2
    ed.tag_add(ed._get_or_create_tag({"bold": True}), "1.0", "1.2")  # a、b 加粗
    ed.mark_set("insert", "1.2")
    ed.insert("1.0", "XY")  # 光标在 1.2，插入点在 1.0（光标前）
    assert ed._style_at("1.0") == {}            # X 带基础样式
    assert ed._style_at("1.1") == {}            # Y 带基础样式
    assert ed._style_at("1.2") == {"bold": True}  # 原 a 保持 bold
    assert ed._style_at("1.3") == {"bold": True}  # 原 b 保持 bold
    assert ed._style_at("1.4") == {}            # 原 c 保持无样式
    for i in ("1.2", "1.3"):
        tags = [t for t in ed.tag_names(i) if t in ed._style_tags]
        assert len(tags) == 1, "既有文本不得被叠加样式标签"


def test_apply_style_no_selection_sets_current_style(tk_root):
    calls = []
    ed = editor.RichTextEditor(tk_root)
    ed.set_on_dirty(lambda: calls.append(1))
    ed.apply_style_to_selection({"size": 20})
    assert ed._current_style.get("size") == 20
    assert calls == [1]


def test_roundtrip_text_and_styles(tk_root):
    ed = editor.RichTextEditor(tk_root)
    ed.insert_plain("Hello")
    ed._apply_delta_range("1.0", "1.5", {"bold": True, "size": 20})
    ed._apply_delta_range("1.0", "1.2", {"fg": "#ff0000"})
    doc = ed.to_document()
    ed2 = editor.RichTextEditor(tk_root)
    ed2.from_document(doc, {})
    assert ed2.to_document() == doc


def test_roundtrip_preserves_styles_dict(tk_root):
    ed = editor.RichTextEditor(tk_root)
    ed.insert_plain("ab")
    ed._apply_delta_range("1.0", "1.1", {"bold": True})
    ed._apply_delta_range("1.1", "1.2", {"italic": True})
    doc = ed.to_document()
    assert "s1" in doc["styles"] and doc["styles"]["s1"] == {"bold": True}
    assert "s2" in doc["styles"] and doc["styles"]["s2"] == {"italic": True}


def test_roundtrip_with_image(tk_root):
    from PIL import Image as PILImage
    import io
    ed = editor.RichTextEditor(tk_root)
    ed.insert_plain("ab")
    img = PILImage.new("RGBA", (40, 30), (255, 0, 0, 255))
    img_id = ed.insert_image(img, max_width=20)
    doc = ed.to_document()
    blobs = ed.get_image_blobs()
    assert img_id in blobs
    # 源图(40x30)被完整保存，而非缩放后的显示图(20x15)
    assert PILImage.open(io.BytesIO(blobs[img_id])).size == (40, 30)
    ed2 = editor.RichTextEditor(tk_root)
    ed2.from_document(doc, blobs)
    assert ed2.to_document() == doc
    # 重开后源图仍为原始分辨率，证明缩放无损
    assert ed2.image_source(img_id).size == (40, 30)


def test_pending_style_survives_cursor_move(tk_root):
    ed = editor.RichTextEditor(tk_root)
    ed.apply_style_to_selection({"size": 20})   # 无选区 -> pending
    assert ed._pending is True
    ed._on_cursor_move()                        # 模拟点击别处
    assert ed._current_style.get("size") == 20  # pending 保护，未被覆盖
    assert ed._pending is True


def test_pending_cleared_by_insert(tk_root):
    ed = editor.RichTextEditor(tk_root)
    ed.apply_style_to_selection({"size": 20})
    ed.insert("end-1c", "H")
    assert ed._pending is False
    assert ed._style_at("1.0").get("size") == 20


def test_loading_path_does_not_consume_pending(tk_root):
    ed = editor.RichTextEditor(tk_root)
    ed.apply_style_to_selection({"size": 20})
    ed.insert_plain("x")
    assert ed._pending is True


def test_cursor_style_callback_fires_with_current_style(tk_root):
    ed = editor.RichTextEditor(tk_root)
    captured = []
    ed.set_on_cursor_style(lambda st: captured.append(st))
    ed.insert_plain("ab")
    ed._apply_delta_range("1.0", "1.1", {"bold": True})
    ed.mark_set("insert", "1.0")
    ed._on_cursor_move()
    assert captured and captured[-1].get("bold") is True


def test_toolbar_size_box_refreshes_on_cursor_move(tk_root):
    import toolbar
    ed = editor.RichTextEditor(tk_root)
    tb = toolbar.FormatToolbar(tk_root)
    tb.set_editor(ed)
    ed.insert_plain("hello")
    ed._apply_delta_range("1.0", "1.2", {"size": 20})
    ed.mark_set("insert", "1.1")
    ed._on_cursor_move()
    assert tb.size_var.get() == "20"
    ed.mark_set("insert", "1.4")
    ed._on_cursor_move()
    assert tb.size_var.get() == str(util.DEFAULT_SIZE)


class _FakeToolbarEditor:
    def __init__(self):
        self.applied = []

    def set_on_cursor_style(self, cb):
        pass

    def apply_style_to_selection(self, delta):
        self.applied.append(delta)


def test_toolbar_size_clamped_to_valid_range(tk_root):
    # 自由输入钳制到 1–400：0/负数（Tk 视为像素字体）与巨大值不再生效
    import toolbar
    ed = _FakeToolbarEditor()
    tb = toolbar.FormatToolbar(tk_root)
    tb.set_editor(ed)
    tb.size_var.set("0")
    tb.on_size()
    tb.size_var.set("-5")
    tb.on_size()
    tb.size_var.set("99999")
    tb.on_size()
    assert ed.applied == [{"size": 1}, {"size": 1}, {"size": 400}]
    assert tb.size_var.get() == "400", "钳制后显示值应回写"
    tb.size_var.set("abc")
    tb.on_size()
    assert len(ed.applied) == 3  # 非数字忽略
    tb.size_var.set("12")
    tb.on_size()
    assert ed.applied[-1] == {"size": 12}


def test_delete_image_removes_from_text_and_registry(tk_root):
    from PIL import Image as PILImage
    ed = editor.RichTextEditor(tk_root)
    ed.insert_plain("ab")
    img = PILImage.new("RGBA", (20, 20), (0, 0, 0, 255))
    img_id = ed.insert_image(img)
    assert img_id in ed._images
    ed.delete_image(img_id)
    assert img_id not in ed._images
    segs = ed.dump("1.0", "end", image=True, text=False, tag=False)
    assert not any(k == "image" for k, _v, _i in segs)


class _FakeKey:
    def __init__(self, char, state=0):
        self.char = char
        self.state = state


def test_typed_char_styled_in_keypress_phase(tk_root):
    # 真实打字：默认 <KeyPress> 类绑定走 Tcl 层 insert 插入裸字。同一 KeyPress 事件
    # 里排在类绑定之后的晚绑定 _stamp_typed_range 立即把 _current_style 套到刚插入
    # 的字上——发生在重绘之前，避免「先旧字号再跳变」的闪烁（Bug 1）。
    ed = editor.RichTextEditor(tk_root)
    ed.apply_style_to_selection({"size": 20})   # 无选区 -> pending
    assert ed._pending is True
    start = ed.index("insert")
    ed._on_key_press(_FakeKey("z"))             # 早绑定：记录打字前光标
    ed.tk.call(ed._w, "insert", "insert", "z")  # 默认类绑定：C 层插入裸字
    ed._stamp_typed_range()                     # 晚绑定：重绘前立即套样式（尚未 KeyRelease）
    assert ed._style_at(start).get("size") == 20
    assert ed._pending is False


def test_late_keypress_handler_registered_after_text_class(tk_root):
    # 晚绑定标签必须排在 "Text" 类绑定之后，保证插字先发生、套样式随后
    ed = editor.RichTextEditor(tk_root)
    tags = ed.bindtags()
    text_idx = tags.index("Text")
    assert ed._late_tag in tags
    assert tags.index(ed._late_tag) > text_idx


def test_typed_text_with_empty_style_adds_no_tag(tk_root):
    # 空基础样式输入的字改为带一个基础样式标签（旧契约是「无标签」）。
    ed = editor.RichTextEditor(tk_root)
    ed.insert_plain("ab")
    ed.mark_set("insert", "end-1c")
    ed._on_key_press(_FakeKey("c"))
    ed.tk.call(ed._w, "insert", "insert", "c")
    ed._stamp_typed_range()
    tags = [t for t in ed.tag_names("1.2") if t in ed._style_tags]
    assert len(tags) == 1
    assert ed._style_tags[tags[0]] == {}


def test_widget_font_tracks_current_style(tk_root):
    # 空行的插入光标高度由控件基础字体决定；让控件字体跟随 _current_style，
    # 这样回车到空行后光标高度与当前字号一致。
    import tkinter.font as tkfont
    ed = editor.RichTextEditor(tk_root)
    ed.apply_style_to_selection({"size": 20})
    assert tkfont.Font(font=ed.cget("font")).actual()["size"] == 20
    ed.apply_style_to_selection({"size": 8})
    assert tkfont.Font(font=ed.cget("font")).actual()["size"] == 8


def test_roundtrip_filters_base_tag(tk_root):
    # 基础样式标签在序列化时被剔除（文件紧凑、向后兼容），往返仍一致。
    ed = editor.RichTextEditor(tk_root)
    ed._on_key_press(_FakeKey("a"))
    ed.tk.call(ed._w, "insert", "insert", "a")
    ed._stamp_typed_range()
    tags = [t for t in ed.tag_names("1.0") if t in ed._style_tags]
    assert len(tags) == 1 and ed._style_tags[tags[0]] == {}
    doc = ed.to_document()
    assert doc["styles"] == {}
    assert [op["k"] for op in doc["ops"]] == ["text"]
    ed2 = editor.RichTextEditor(tk_root)
    ed2.from_document(doc, {})
    assert ed2.to_document() == doc


def test_from_document_tags_untagged_base(tk_root):
    # 加载含无标签正文的（旧）文件时，内部补上基础标签，避免控件字体变化时污染。
    ed = editor.RichTextEditor(tk_root)
    ed.insert_plain("ab")
    doc = ed.to_document()
    assert doc["styles"] == {}
    ed2 = editor.RichTextEditor(tk_root)
    ed2.from_document(doc, {})
    tags = [t for t in ed2.tag_names("1.0") if t in ed2._style_tags]
    assert len(tags) == 1 and ed2._style_tags[tags[0]] == {}
    assert ed2.to_document() == doc


def test_typed_after_selection_format_excludes_applied_attr(tk_root):
    # Bug 2：对选区应用 加粗/斜体/删除线/颜色 后，紧随其后输入的文字不应带上该效果。
    ed = editor.RichTextEditor(tk_root)
    ed.insert_plain("ab")
    ed._apply_delta_range("1.0", "1.2", {"size": 14})   # 周围文字为 14 号
    ed.tag_add("sel", "1.0", "1.1")                      # 选中 "a"
    ed.mark_set("insert", "1.1")                         # 光标在选区末尾
    ed.apply_style_to_selection({"bold": True})          # 把 "a" 加粗
    # 后续输入样式 = 周围样式(14号) 去掉本次应用的属性(bold)
    assert ed._current_style.get("size") == 14
    assert not ed._current_style.get("bold")
    assert ed._pending is True
    # 模拟用户点击选区后面定位光标（清选区）再输入：pending 保护样式不被覆盖
    ed.tag_remove("sel", "1.0", "end")
    ed.mark_set("insert", "1.1")
    ed._on_cursor_move()
    assert ed._current_style.get("size") == 14
    assert not ed._current_style.get("bold")
    ed._on_key_press(_FakeKey("X"))
    ed.tk.call(ed._w, "insert", "insert", "X")
    ed._stamp_typed_range()
    assert ed._style_at("1.1").get("size") == 14   # 保留周围字号
    assert not ed._style_at("1.1").get("bold")      # 不带刚应用的加粗


def test_typed_after_color_selection_excludes_color(tk_root):
    # Bug 2：换颜色只作用于选区，后续输入不带该颜色
    ed = editor.RichTextEditor(tk_root)
    ed.insert_plain("ab")
    ed.tag_add("sel", "1.0", "1.1")
    ed.mark_set("insert", "1.1")
    ed.apply_style_to_selection({"fg": "#ff0000"})
    assert not ed._current_style.get("fg")
    ed.tag_remove("sel", "1.0", "end")
    ed.mark_set("insert", "1.1")
    ed._on_cursor_move()
    ed._on_key_press(_FakeKey("X"))
    ed.tk.call(ed._w, "insert", "insert", "X")
    ed._stamp_typed_range()
    assert not ed._style_at("1.1").get("fg")


def test_set_line_spacing_configures_spacing(tk_root):
    ed = editor.RichTextEditor(tk_root)
    ed.set_line_spacing(4)
    assert int(ed.cget("spacing1")) == 4
    assert int(ed.cget("spacing2")) == 4
    assert int(ed.cget("spacing3")) == 0


def test_sync_ime_font_does_not_crash_across_style_changes(tk_root):
    # 输入法预编辑窗字体同步在样式/光标变化时调用，绝不应抛异常；
    # 具体预编辑观感需在带输入法的 Windows 桌面人工验证。
    ed = editor.RichTextEditor(tk_root)
    ed.insert_plain("ab")
    ed._apply_delta_range("1.0", "1.2", {"size": 20, "bold": True})
    ed.mark_set("insert", "1.1")
    ed._on_cursor_move()                 # 进入 20 号粗体区域
    ed.mark_set("insert", "1.0")
    ed._on_cursor_move()
    ed.apply_style_to_selection({"italic": True})  # 无选区 -> pending
    ed.mark_set("insert", "end-1c")
    ed._on_cursor_move()
    # _ime_style 要么仍未同步(None，控件未真正显示)，要么记录了最后一次样式
    assert ed._ime_style is None or ed._ime_style.get("size") in (None, 20)


def test_delete_marks_dirty(tk_root):
    # 关键数据丢失修复：Backspace/Delete/Ctrl+X 等 Tcl 层删除绕过 Python insert()
    # 覆写，必须经 <<Modified>> 虚拟事件兜底标脏。
    ed = editor.RichTextEditor(tk_root)
    ed.insert("end", "hello")
    seen = []
    ed.set_on_dirty(lambda: seen.append(1))
    ed.tk.call(ed._w, "delete", "1.0", "1.3")   # 模拟 Tcl 层删除（Backspace/剪切同路径）
    tk_root.update()                             # 派发 <<Modified>> 虚拟事件
    assert seen, "Tcl 层删除未触发 dirty"


def test_from_document_not_dirty(tk_root):
    import snote
    ed = editor.RichTextEditor(tk_root)
    doc = snote.build_document({}, [{"k": "text", "text": "载入的内容"}], {})
    ed.from_document(doc, {})
    tk_root.update()
    seen = []
    ed.set_on_dirty(lambda: seen.append(1))
    ed.tk.call(ed._w, "delete", "1.0", "1.1")
    tk_root.update()
    assert seen, "载入后应能正常标脏（说明 _loading 未卡死）"
    # 再验证载入本身不脏：新建一个，载入后不操作，不应有脏回调
    ed2 = editor.RichTextEditor(tk_root)
    seen2 = []
    ed2.set_on_dirty(lambda: seen2.append(1))
    ed2.from_document(doc, {})
    tk_root.update()
    assert not seen2, "载入文档不应标脏"


def test_paste_text_is_tagged(tk_root):
    # 文本粘贴走 Tcl 类绑定插字（绕过 Python insert()），晚绑定必须补打标签，
    # 否则正文出现无标签字符，控件字体随 _current_style 变化时会污染粘贴文本。
    ed = editor.RichTextEditor(tk_root)
    ed.insert("end", "ab")
    ed.mark_set("insert", "end-1c")
    ed.clipboard_clear()
    ed.clipboard_append("XY")
    ed.event_generate("<<Paste>>")
    tk_root.update()
    tags = [t for t in ed.tag_names("end-2c") if t in ed._style_tags]
    assert tags, "粘贴的文本未打标签"


def test_paste_over_selection_is_tagged(tk_root):
    # 粘贴覆盖选区时 tk_textPaste 会删选区并从 sel.first 插入；若以 insert mark
    # （sel.last）记录起点，粘贴后 insert 索引未前进，晚绑定补标会失效。
    from editor import RichTextEditor
    ed = RichTextEditor(tk_root)
    ed.insert("end", "abcd")
    ed.tag_add("sel", "1.2", "1.4")
    ed.mark_set("insert", "1.4")
    ed.clipboard_clear()
    ed.clipboard_append("XY")
    ed.event_generate("<<Paste>>")
    tk_root.update()
    # 选区被替换，粘贴的两字符都需带样式标签
    tags = [t for t in ed.tag_names("1.2") if t in ed._style_tags]
    assert tags, "粘贴覆盖选区后文本未打标签"
    tags2 = [t for t in ed.tag_names("1.3") if t in ed._style_tags]
    assert tags2, "粘贴覆盖选区后第二个字符未打标签"


def test_undo_marks_dirty(tk_root):
    # 撤销走 Tcl 级 edit undo（Ctrl+Z 经 <<Undo>> 类绑定同路径；event_generate
    # "<Control-z>" 不做 keymap 翻译、不会执行撤销）。先 update 派发插入产生的
    # <<Modified>>（真实 mainloop 行为），否则残留事件先于撤销生效、断言失真。
    from editor import RichTextEditor
    ed = RichTextEditor(tk_root)
    ed.insert("end", "abc")
    tk_root.update()
    seen = []
    ed.set_on_dirty(lambda: seen.append(1))
    ed.tk.call(ed._w, "edit", "undo")
    tk_root.update()
    assert seen, "撤销未触发 dirty"


# ---- 样式标签 O(1) 反查（_style_tag_lookup）----

def test_get_or_create_tag_reuses_tag_for_equal_style(tk_root):
    # 样式相等（dict 相等）即同一标签；lookup 与 _style_tags 双向一致
    ed = editor.RichTextEditor(tk_root)
    t1 = ed._get_or_create_tag({"bold": True})
    t2 = ed._get_or_create_tag({"bold": True})
    assert t1 == t2
    t3 = ed._get_or_create_tag({"bold": True, "size": 20})
    assert t3 != t1
    assert ed._style_tag_lookup[editor.RichTextEditor._style_key({"bold": True})] == t1
    assert ed._style_tags[t1] == {"bold": True}


def test_style_tag_lookup_synced_after_from_document(tk_root):
    # from_document 直接写 _style_tags 的路径必须同步 lookup；载入后按同样式
    # 取标签应命中载入的标签而不是新建（数量不增长）
    ed = editor.RichTextEditor(tk_root)
    ed.insert_plain("ab")
    ed._apply_delta_range("1.0", "1.1", {"bold": True})
    doc = ed.to_document()
    ed2 = editor.RichTextEditor(tk_root)
    ed2.from_document(doc, {})
    assert len(ed2._style_tags) == len(ed2._style_tag_lookup)
    for tag, style in ed2._style_tags.items():
        assert ed2._style_tag_lookup[editor.RichTextEditor._style_key(style)] == tag
    n = len(ed2._style_tags)
    t = ed2._get_or_create_tag({"bold": True})
    assert ed2._style_tags[t] == {"bold": True}
    assert len(ed2._style_tags) == n
    assert len(ed2._style_tags) == len(ed2._style_tag_lookup)


# ---- 图片编码缓存 + 双击局部定位 ----

def test_get_image_blobs_caches_encoding(tk_root):
    from PIL import Image as PILImage
    ed = editor.RichTextEditor(tk_root)
    ed.insert_plain("ab")
    img = PILImage.new("RGBA", (40, 30), (255, 0, 0, 255))
    img_id = ed.insert_image(img, max_width=20)
    assert img_id not in ed._image_encoded  # 首次保存前不预编码
    blobs1 = ed.get_image_blobs()
    assert img_id in ed._image_encoded
    assert ed._image_encoded[img_id] == blobs1[img_id]
    blobs2 = ed.get_image_blobs()
    assert blobs2 == blobs1
    assert blobs2[img_id] is blobs1[img_id]  # 二次调用命中缓存，同一字节对象


def test_image_encoding_cache_invalidated_on_reload(tk_root):
    import io
    from PIL import Image as PILImage
    ed = editor.RichTextEditor(tk_root)
    ed.insert_plain("ab")
    img = PILImage.new("RGBA", (40, 30), (255, 0, 0, 255))
    img_id = ed.insert_image(img)
    blobs = ed.get_image_blobs()
    assert ed._image_encoded.get(img_id) is not None
    doc = ed.to_document()
    ed2 = editor.RichTextEditor(tk_root)
    ed2.from_document(doc, blobs)
    assert img_id in ed2._images
    assert img_id not in ed2._image_encoded  # 载入不预编码，首次保存时才编码
    b2 = ed2.get_image_blobs()
    assert PILImage.open(io.BytesIO(b2[img_id])).size == (40, 30)
    assert ed2._image_encoded.get(img_id) is not None


def test_delete_image_clears_encoding_cache(tk_root):
    from PIL import Image as PILImage
    ed = editor.RichTextEditor(tk_root)
    ed.insert_plain("ab")
    img_id = ed.insert_image(PILImage.new("RGBA", (20, 20), (0, 0, 0, 255)))
    ed.get_image_blobs()
    assert img_id in ed._image_encoded
    ed.delete_image(img_id)
    assert img_id not in ed._image_encoded


class _FakeClick:
    def __init__(self, x, y):
        self.x = x
        self.y = y


def test_double_click_on_image_starts_resize(tk_root):
    # 双击图片：局部 dump（点击处 +1c）命中图片，以 img_id 进入缩放
    import tkinter as tk
    from PIL import Image as PILImage
    top = tk.Toplevel(tk_root)
    ed = editor.RichTextEditor(top)
    ed.pack()
    tk_root.update()
    try:
        ed.insert_plain("ab")
        img_id = ed.insert_image(PILImage.new("RGBA", (40, 30), (255, 0, 0, 255)))
        idx = ed._index_of_image(img_id)
        bbox = ed.bbox(idx)
        assert bbox is not None
        clicked = []
        ed.begin_resize = lambda i: clicked.append(i)
        result = ed._on_double_click(_FakeClick(bbox[0] + 1, bbox[1] + 1))
        assert result == "break"
        assert clicked == [img_id]
    finally:
        top.destroy()


def test_double_click_on_text_does_not_resize(tk_root):
    # 双击正文：局部 dump 无图片事件，不进入缩放、不拦截默认行为
    import tkinter as tk
    from PIL import Image as PILImage
    top = tk.Toplevel(tk_root)
    ed = editor.RichTextEditor(top)
    ed.pack()
    tk_root.update()
    try:
        ed.insert_plain("ab")
        ed.insert_image(PILImage.new("RGBA", (40, 30), (255, 0, 0, 255)))
        bbox = ed.bbox("1.0")
        assert bbox is not None
        clicked = []
        ed.begin_resize = lambda i: clicked.append(i)
        result = ed._on_double_click(_FakeClick(bbox[0] + 1, bbox[1] + 1))
        assert result is None
        assert clicked == []
    finally:
        top.destroy()


def _open_resizer(tk_root):
    import tkinter as tk
    from PIL import Image as PILImage
    top = tk.Toplevel(tk_root)
    ed = editor.RichTextEditor(top)
    ed.pack()
    tk_root.update()
    ed.insert_plain("ab")
    img_id = ed.insert_image(PILImage.new("RGBA", (40, 30), (255, 0, 0, 255)))
    ed.begin_resize(img_id)
    tk_root.update()
    return top, ed, img_id


def test_resizer_toplevel_uses_editor_master(tk_root):
    # 缩放浮层 Toplevel 必须挂在编辑器所属顶层下，而非隐式默认 root
    top, ed, _img_id = _open_resizer(tk_root)
    try:
        assert ed._resizer is not None
        assert ed._resizer.win.master is top
    finally:
        top.destroy()


def test_resizer_focusout_does_not_auto_confirm(tk_root):
    # 焦点离开不再自动确认缩放（只能 Enter 确认 / Esc、Delete 取消）
    top, ed, img_id = _open_resizer(tk_root)
    try:
        r = ed._resizer
        assert not r.canvas.bind("<FocusOut>")
        r._confirm()
        assert ed._resizer is None
        assert ed.image_display_size(img_id) == (40, 30)
    finally:
        top.destroy()


def test_resizer_cancel_restores_original_size(tk_root):
    top, ed, img_id = _open_resizer(tk_root)
    try:
        ed._resizer._cancel()
        assert ed._resizer is None
        assert ed.image_display_size(img_id) == (40, 30)  # 恢复原尺寸
    finally:
        top.destroy()


def test_find_matches_counts_and_case(tk_root):
    ed = editor.RichTextEditor(tk_root)
    ed.insert_plain("Foo foo FOO bar")
    assert len(ed.find_matches("foo", case=False)) == 3
    assert len(ed.find_matches("foo", case=True)) == 1
    assert ed.find_matches("xyz", case=False) == []


def test_find_matches_empty_pattern(tk_root):
    ed = editor.RichTextEditor(tk_root)
    ed.insert_plain("abc")
    assert ed.find_matches("", case=False) == []


def test_search_next_wraps_and_reports_position(tk_root):
    ed = editor.RichTextEditor(tk_root)
    ed.insert_plain("a b a b a")
    assert ed.search_next("a", case=True) == (1, 3)
    assert ed.search_next("a", case=True) == (2, 3)
    assert ed.search_next("a", case=True) == (3, 3)
    assert ed.search_next("a", case=True) == (1, 3)  # 环绕回首个


def test_search_prev_wraps(tk_root):
    # 依赖 Tk 语义：backwards 搜索不命中起点处的匹配，故从 sel.first 起搜不原地重复
    ed = editor.RichTextEditor(tk_root)
    ed.insert_plain("a b a")
    assert ed.search_prev("a", case=True) == (2, 2)
    assert ed.search_prev("a", case=True) == (1, 2)
    assert ed.search_prev("a", case=True) == (2, 2)  # 环绕回末尾


def test_search_next_no_match_returns_none(tk_root):
    ed = editor.RichTextEditor(tk_root)
    ed.insert_plain("abc")
    assert ed.search_next("z", case=False) is None


def test_search_empty_pattern_clears(tk_root):
    ed = editor.RichTextEditor(tk_root)
    ed.insert_plain("a a")
    ed.search_next("a", case=True)
    assert ed.search_next("", case=True) is None
    assert not ed.tag_ranges("search_all")


def test_search_highlights_and_clear(tk_root):
    ed = editor.RichTextEditor(tk_root)
    ed.insert_plain("x y x")
    ed.search_next("x", case=True)
    assert ed.tag_ranges("search_all")   # 全部匹配有底纹
    assert ed.tag_ranges("search_cur")   # 当前匹配有底纹
    ed.clear_search_highlight()
    assert not ed.tag_ranges("search_all")
    assert not ed.tag_ranges("search_cur")


def test_highlight_refreshes_on_pattern_change(tk_root):
    ed = editor.RichTextEditor(tk_root)
    ed.insert_plain("a x b x c")
    ed.search_next("a", case=True)
    ed.search_next("x", case=True)
    # 旧 pattern 的底纹被移除，新 pattern 的两处匹配有底纹
    ranges = ed.tag_ranges("search_all")  # 扁平 (start1, end1, start2, end2)
    assert len(ranges) == 4
    assert ed.get(ranges[0], ranges[1]) == "x"
    assert ed.get(ranges[2], ranges[3]) == "x"


def test_search_highlight_not_serialized(tk_root):
    ed = editor.RichTextEditor(tk_root)
    ed.insert_plain("a b a")
    ed.search_next("a", case=True)
    doc = ed.to_document()
    assert "search_all" not in str(doc)
    assert "search_cur" not in str(doc)


def test_search_jump_syncs_current_style(tk_root):
    # 查找跳转移动光标后，_current_style 跟随光标处样式（续写样式/工具栏同步）
    ed = editor.RichTextEditor(tk_root)
    ed.insert_plain("aa bb aa")
    ed._apply_delta_range("1.3", "1.5", {"size": 30})  # "aa bb aa" 中 "bb" 占 1.3-1.5
    ed.search_next("bb", case=True)  # 光标跳入 1.3-1.5 的 size:30 区域
    assert ed._current_style.get("size") == 30
    assert ed._style_at(ed.index("insert")).get("size") == 30
