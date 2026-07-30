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


def test_insert_no_style_when_current_empty(tk_root):
    ed = editor.RichTextEditor(tk_root)
    ed.insert("end-1c", "Hi")
    tags = [t for t in ed.tag_names("1.0") if t in ed._style_tags]
    assert tags == []


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


def test_typed_text_receives_pending_style(tk_root):
    # 真实打字走默认 <KeyPress> 类绑定 -> Tcl 层 insert，绕过 Python insert 重写。
    # 模拟该路径：KeyPress 记录起点 -> Tcl 层 insert 插字 -> KeyRelease 套样式。
    ed = editor.RichTextEditor(tk_root)
    ed.apply_style_to_selection({"size": 20})   # 无选区 -> pending
    assert ed._pending is True
    start = ed.index("insert")
    ed._on_key_press(_FakeKey("z"))             # 记录打字前光标
    ed.tk.call(ed._w, "insert", "insert", "z")  # 默认绑定的 C 层 insert
    ed._on_cursor_move()                        # KeyRelease 把 pending 套到刚输入的字
    assert ed._style_at(start).get("size") == 20
    assert ed._pending is False


def test_typed_text_with_empty_style_adds_no_tag(tk_root):
    ed = editor.RichTextEditor(tk_root)
    ed.insert_plain("ab")
    ed.mark_set("insert", "end-1c")
    ed._on_key_press(_FakeKey("c"))
    ed.tk.call(ed._w, "insert", "insert", "c")
    ed._on_cursor_move()
    tags = [t for t in ed.tag_names("1.2") if t in ed._style_tags]
    assert tags == []


def test_set_line_spacing_configures_spacing(tk_root):
    ed = editor.RichTextEditor(tk_root)
    ed.set_line_spacing(4)
    assert int(ed.cget("spacing1")) == 4
    assert int(ed.cget("spacing2")) == 4
    assert int(ed.cget("spacing3")) == 0
