import todo_panel
from todo_panel import TodoPanel


def _sample():
    return [
        {"id": "a", "text": "任务A", "done": False, "pomo": 2},
        {"id": "b", "text": "任务B", "done": True, "pomo": 0},
    ]


def test_set_items_renders_marks_pomo_and_focus_text(tk_root):
    panel = TodoPanel(tk_root)
    try:
        panel.set_items(_sample(), "a", False)
        kids = panel._tree.get_children()
        assert panel._tree.item(kids[0], "text") == "▶☐"
        assert panel._tree.item(kids[0], "values")[0] == "任务A（🍅×2）"
        assert panel._tree.item(kids[1], "text") == "☑"
        assert panel._tree.item(kids[1], "values")[0] == "任务B"
        assert panel._focus_btn.cget("text") == "开始专注"
        panel.set_items(_sample(), None, True)   # 切换 current/running 后重绘
        assert panel._tree.item(panel._tree.get_children()[0], "text") == "☐"
        assert panel._focus_btn.cget("text") == "停止专注"
    finally:
        panel.destroy()


def test_row_callbacks_dispatch_selected_id(tk_root):
    calls = {"toggle": [], "current": [], "move": [], "remove": []}
    focus = []
    panel = TodoPanel(
        tk_root,
        on_toggle=lambda tid: calls["toggle"].append(tid),
        on_set_current=lambda tid: calls["current"].append(tid),
        on_move=lambda tid, d: calls["move"].append((tid, d)),
        on_remove=lambda tid: calls["remove"].append(tid),
        on_toggle_focus=lambda: focus.append(1),
    )
    try:
        panel.set_items(_sample(), None, False)
        panel._select_id("b")
        panel._on_double_click(None)
        panel._menu_toggle()
        panel._menu_set_current()
        panel._menu_move(-1)
        panel._menu_remove()
        panel._menu_clear_current()
        panel._on_focus()
        assert calls["toggle"] == ["b", "b"]
        assert calls["current"] == ["b", None]
        assert calls["move"] == [("b", -1)]
        assert calls["remove"] == ["b"]
        assert focus == [1]
    finally:
        panel.destroy()


def test_add_empty_text_shows_info_and_skips_callback(tk_root, monkeypatch):
    shown = []
    monkeypatch.setattr(todo_panel.messagebox, "showinfo", lambda *a, **k: shown.append(a))
    added = []
    panel = TodoPanel(tk_root, on_add=added.append)
    try:
        panel._entry_var.set("   ")
        panel._on_add()
        assert shown and added == []      # 空文本提示且不回调
        panel._entry_var.set(" 新任务 ")
        panel._on_add()
        assert added == ["新任务"]        # strip 后回调
        assert panel._entry_var.get() == ""  # 添加后清空输入框
    finally:
        panel.destroy()


def test_set_items_preserves_selection_across_refresh(tk_root):
    panel = TodoPanel(tk_root)
    try:
        panel.set_items(_sample(), None, False)
        panel._select_id("b")
        panel.set_items(_sample(), None, False)
        assert panel._selected_id() == "b"
    finally:
        panel.destroy()
