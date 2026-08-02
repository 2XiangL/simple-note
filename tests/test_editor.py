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
