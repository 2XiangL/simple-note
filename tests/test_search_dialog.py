import editor
from search_dialog import SearchDialog


def _make(tk_root, text):
    ed = editor.RichTextEditor(tk_root)
    ed.insert_plain(text)
    dlg = SearchDialog(tk_root, lambda: ed)
    return ed, dlg


def test_dialog_next_cycles_matches(tk_root):
    ed, dlg = _make(tk_root, "a b a")
    dlg._var.set("a")
    dlg._find_next()
    assert dlg._status.cget("text") == "1/2"
    dlg._find_next()
    assert dlg._status.cget("text") == "2/2"
    dlg._find_next()
    assert dlg._status.cget("text") == "1/2"  # 环绕


def test_dialog_prev_goes_backwards(tk_root):
    ed, dlg = _make(tk_root, "a b a")
    dlg._var.set("a")
    dlg._find_next()
    dlg._find_next()
    assert dlg._status.cget("text") == "2/2"
    dlg._find_prev()
    assert dlg._status.cget("text") == "1/2"


def test_dialog_entry_change_shows_count(tk_root):
    ed, dlg = _make(tk_root, "x y x")
    dlg._var.set("x")  # trace_add 同步触发 _on_entry_change
    assert "2" in dlg._status.cget("text")
    dlg._var.set("zzz")
    assert dlg._status.cget("text") == "无匹配"


def test_dialog_close_clears_highlight(tk_root):
    ed, dlg = _make(tk_root, "a a")
    dlg._var.set("a")
    dlg._find_next()
    assert ed.tag_ranges("search_all")
    dlg._on_close()
    assert not ed.tag_ranges("search_all")
    assert not dlg.winfo_exists()


def test_dialog_case_toggle_recounts(tk_root):
    ed, dlg = _make(tk_root, "A a A")
    dlg._var.set("a")
    assert "3" in dlg._status.cget("text")
    dlg._case_var.set(True)  # 触发 command -> _on_entry_change
    assert dlg._status.cget("text") == "共 1 处"


def test_dialog_empty_pattern_clears_status_and_highlight(tk_root):
    ed, dlg = _make(tk_root, "a a")
    dlg._var.set("a")
    dlg._find_next()
    assert ed.tag_ranges("search_all")
    dlg._var.set("")
    assert dlg._status.cget("text") == ""
    assert not ed.tag_ranges("search_all")


def test_dialog_provider_none_is_safe(tk_root):
    dlg = SearchDialog(tk_root, lambda: None)
    dlg._var.set("a")
    dlg._find_next()  # 不抛
    dlg._on_close()   # 不抛


def test_dialog_refresh_after_editor_switch(tk_root):
    # 文档切换后 refresh()：状态按新编辑器重算，且旧编辑器高亮被清
    ed1 = editor.RichTextEditor(tk_root)
    ed1.insert_plain("a a a")
    ed2 = editor.RichTextEditor(tk_root)
    ed2.insert_plain("b")
    current = [ed1]
    dlg = SearchDialog(tk_root, lambda: current[0])
    dlg._var.set("a")
    dlg._find_next()
    assert dlg._status.cget("text") == "1/3"
    current[0] = ed2
    dlg.refresh()
    assert dlg._status.cget("text") == "无匹配"
    assert not ed1.tag_ranges("search_all")


def test_dialog_close_clears_last_highlighted_editor(tk_root):
    # 在 A 上查找后切到 B，关闭对话框应清掉 A 的高亮
    ed1 = editor.RichTextEditor(tk_root)
    ed1.insert_plain("x y x")
    ed2 = editor.RichTextEditor(tk_root)
    ed2.insert_plain("y")
    current = [ed1]
    dlg = SearchDialog(tk_root, lambda: current[0])
    dlg._var.set("x")
    dlg._find_next()
    assert ed1.tag_ranges("search_all")
    current[0] = ed2
    dlg._on_close()
    assert not ed1.tag_ranges("search_all")
    assert not dlg.winfo_exists()
