import lang
from notes_panel import NotesPanel


class _FakeDoc:
    def __init__(self, title):
        self.title = title
        self.dirty = False

    @property
    def display_title(self):
        return ("*" if self.dirty else "") + self.title


def _panel(tk_root):
    return NotesPanel(tk_root)


def test_remove_unselected_keeps_selection(tk_root):
    # 移除未选中行：Tk 单选 selection 跟随索引，原选中项保持
    p = _panel(tk_root)
    d1, d2, d3 = _FakeDoc("a"), _FakeDoc("b"), _FakeDoc("c")
    p.add(d1)
    p.add(d2)
    p.add(d3)
    p.select(d2)
    p.remove(d1)
    assert p.selected_doc() is d2
    assert p.listbox.curselection() == (0,)


def test_remove_selected_reselects_first(tk_root):
    p = _panel(tk_root)
    d1, d2 = _FakeDoc("a"), _FakeDoc("b")
    p.add(d1)
    p.add(d2)
    p.select(d2)
    p.remove(d2)
    assert p.selected_doc() is d1


def test_remove_last_leaves_no_selection(tk_root):
    p = _panel(tk_root)
    d1 = _FakeDoc("a")
    p.add(d1)
    p.remove(d1)
    assert p.selected_doc() is None
    assert p.listbox.curselection() == ()


def test_remove_unknown_doc_is_noop(tk_root):
    p = _panel(tk_root)
    d1 = _FakeDoc("a")
    p.add(d1)
    p.remove(_FakeDoc("不在列表"))
    assert p.selected_doc() is d1


def test_context_menu_english_in_en_mode(tk_root):
    lang.set_language("en")
    try:
        p = _panel(tk_root)
        labels = [p.menu.entrycget(i, "label") for i in range(p.menu.index("end") + 1)
                  if p.menu.type(i) != "separator"]
        assert labels == ["Save", "Save As", "Close"]
    finally:
        lang.set_language("zh")
