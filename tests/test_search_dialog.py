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
