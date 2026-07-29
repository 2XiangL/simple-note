import editor


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
