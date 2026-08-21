import os
import sys
from datetime import datetime, timedelta
from tkinter import ttk
from types import SimpleNamespace

import pytest

import lang
import reminder
import settings
import todo
from app import NoteApp


class _FakeDoc:
    def __init__(self, path):
        self.path = path
        self.dirty = False


def test_open_doc_dedupes_already_open_path(tmp_path, monkeypatch):
    # 打开已在 docs 中的路径：直接 switch_to 该文档，不重新 load、不新建
    from app import NoteApp
    f = tmp_path / "a.snote"
    f.write_bytes(b"x")
    app = NoteApp.__new__(NoteApp)
    existing = _FakeDoc(path=str(f))
    app.docs = [existing]
    calls = []
    app.switch_to = lambda d: calls.append(("switch", d))
    monkeypatch.setattr("app.filedialog.askopenfilename", lambda **k: str(f))
    monkeypatch.setattr("app.snote.load_document", lambda p: calls.append(("load", p)))
    app.open_doc()
    assert calls == [("switch", existing)]


@pytest.mark.skipif(sys.platform != "win32", reason="normcase 大小写折叠仅 Windows")
def test_open_doc_dedupes_by_realpath_case(tmp_path, monkeypatch):
    # 同一文件的不同写法（大小写/相对路径）仍判重；POSIX 上 normcase 恒等，
    # 该用例仅 Windows 有意义（避免未来 CI 误报）
    from app import NoteApp
    f = tmp_path / "CaseTest.snote"
    f.write_bytes(b"x")
    app = NoteApp.__new__(NoteApp)
    existing = _FakeDoc(path=os.path.join(str(tmp_path), "casetest.SNOTE"))
    app.docs = [existing]
    calls = []
    app.switch_to = lambda d: calls.append(d)
    monkeypatch.setattr("app.filedialog.askopenfilename", lambda **k: str(f))
    monkeypatch.setattr("app.snote.load_document", lambda p: calls.append(("load", p)))
    app.open_doc()
    assert calls == [existing]


def test_open_doc_ignores_unsaved_docs_in_dedupe(tmp_path, monkeypatch):
    # doc.path 为 None（未保存）的文档不参与判重，正常走加载流程
    from app import NoteApp
    f = tmp_path / "b.snote"
    f.write_bytes(b"x")
    app = NoteApp.__new__(NoteApp)
    app.docs = [_FakeDoc(path=None)]
    loaded = []
    made = []
    monkeypatch.setattr("app.filedialog.askopenfilename", lambda **k: str(f))
    monkeypatch.setattr("app.snote.load_document", lambda p: loaded.append(p) or ({}, {}))
    monkeypatch.setattr(app, "_make_doc", lambda **kw: made.append(kw) or SimpleNamespace())
    monkeypatch.setattr(app, "add_doc", lambda d: None)
    app.open_doc()
    assert loaded == [str(f)]
    assert made and made[0]["path"] == str(f)


def test_make_doc_destroys_editor_when_from_document_fails(tk_root, monkeypatch):
    # from_document 抛错时编辑器必须被销毁，避免孤儿控件泄漏
    import app as appmod
    from app import NoteApp
    app = NoteApp.__new__(NoteApp)
    app.editor_host = tk_root
    app._line_spacing = settings.DEFAULT_LINE_SPACING
    destroyed = []

    class _Spy(appmod.RichTextEditor):
        def destroy(self):
            destroyed.append(self)
            super().destroy()

    monkeypatch.setattr(appmod, "RichTextEditor", _Spy)
    bad = {"styles": {}, "ops": [], "images": "not-a-dict"}  # from_document 抛错
    with pytest.raises(Exception):
        app._make_doc(document=bad, blobs={})
    assert len(destroyed) == 1, "载入失败后编辑器未被销毁"
    # 正常文档不受影响：不销毁、返回可用 doc
    ok = app._make_doc(document={"styles": {}, "ops": [{"k": "text", "text": "x"}], "images": {}}, blobs={})
    assert len(destroyed) == 1
    assert ok.editor is not None


def test_write_to_catches_non_oserror(tmp_path, monkeypatch):
    # to_document/get_image_blobs 的 PIL/Tcl 异常同样走“保存失败”弹框，不裸抛
    from app import NoteApp
    app = NoteApp.__new__(NoteApp)
    shown = []
    monkeypatch.setattr("app.messagebox.showerror", lambda *a, **k: shown.append(a))

    class _Ed:
        def to_document(self):
            raise RuntimeError("PIL 编码失败")

        def get_image_blobs(self):
            return {}

    doc = SimpleNamespace(editor=_Ed())
    assert app._write_to(doc, str(tmp_path / "x.snote")) is False
    assert shown, "保存异常未弹框"


def test_make_doc_wires_vertical_scrollbar(tk_root):
    # 每个文档容器内含 editor 与纵向滚动条，且二者互绑
    import settings
    from app import NoteApp
    app = NoteApp.__new__(NoteApp)
    app.editor_host = tk_root
    app._line_spacing = settings.DEFAULT_LINE_SPACING
    doc = app._make_doc()
    frame = doc.frame
    children = frame.winfo_children()
    assert doc.editor in children
    sbs = [c for c in children if c.winfo_class() == "TScrollbar"]
    assert len(sbs) == 1
    assert doc.editor.cget("yscrollcommand")  # editor -> sb.set
    assert sbs[0].cget("command")             # sb -> editor.yview


def test_open_search_dialog_singleton(tk_root):
    # 对话框单例复用：已存在则 lift，销毁后可重建
    from app import NoteApp
    app = NoteApp.__new__(NoteApp)
    app.root = tk_root
    app.active = None
    app._search_dlg = None
    app._open_search_dialog()
    first = app._search_dlg
    assert first is not None and first.winfo_exists()
    app._open_search_dialog()
    assert app._search_dlg is first
    first.destroy()
    app._open_search_dialog()
    assert app._search_dlg is not first


def test_switch_to_refreshes_search_dialog(tk_root):
    # 文档切换时查找对话框重算状态/高亮
    import settings
    from app import NoteApp
    app = NoteApp.__new__(NoteApp)
    app.editor_host = tk_root
    app._line_spacing = settings.DEFAULT_LINE_SPACING
    d1 = app._make_doc()
    d2 = app._make_doc()
    app.docs = [d1, d2]
    app.active = None
    app.panel = SimpleNamespace(select=lambda d: None)
    app.toolbar = SimpleNamespace(set_editor=lambda e: None)
    calls = []
    app._search_dlg = SimpleNamespace(winfo_exists=lambda: True, refresh=lambda: calls.append(1))
    app.switch_to(d2)
    assert calls == [1]


def test_open_search_dialog_lift_branch(tk_root):
    # 已存在对话框时重开：lift + focus_entry，不新建
    from app import NoteApp
    from search_dialog import SearchDialog

    class _SpyDlg(SearchDialog):
        def __init__(self, *a, **k):
            self.lifted = 0
            self.focused = 0
            super().__init__(*a, **k)

        def lift(self):
            self.lifted += 1

        def focus_entry(self):
            self.focused += 1

    app = NoteApp.__new__(NoteApp)
    app.root = tk_root
    app.active = None
    app._search_dlg = None
    real = SearchDialog
    try:
        import app as appmod
        appmod.SearchDialog = _SpyDlg
        app._open_search_dialog()
        first = app._search_dlg
        assert first.lifted == 0 and first.focused == 1  # 新建时只 focus
        app._open_search_dialog()
        assert app._search_dlg is first
        assert first.lifted == 1 and first.focused == 2  # 重开时 lift + focus
    finally:
        appmod.SearchDialog = real


def test_switch_to_without_search_dialog(tk_root):
    # _search_dlg 为 None 或已销毁时 switch_to 不崩
    import settings
    from app import NoteApp
    app = NoteApp.__new__(NoteApp)
    app.editor_host = tk_root
    app._line_spacing = settings.DEFAULT_LINE_SPACING
    d1 = app._make_doc()
    d2 = app._make_doc()
    app.docs = [d1, d2]
    app.active = None
    app.panel = SimpleNamespace(select=lambda d: None)
    app.toolbar = SimpleNamespace(set_editor=lambda e: None)
    app._search_dlg = None
    app.switch_to(d2)  # 不抛
    app._search_dlg = SimpleNamespace(winfo_exists=lambda: False, refresh=lambda: None)
    app.switch_to(d1)  # 不抛、不调用 refresh


def test_close_active_doc_with_search_dialog_open(tk_root):
    # 查找对话框开着时关闭当前活动文档：不抛异常、新活动文档无陈旧高亮
    import settings
    from app import NoteApp
    app = NoteApp.__new__(NoteApp)
    app.root = tk_root
    app.editor_host = tk_root
    app._line_spacing = settings.DEFAULT_LINE_SPACING
    d1 = app._make_doc()
    d2 = app._make_doc()
    d1.editor.insert_plain("hello hello")
    d2.editor.insert_plain("world")
    app.docs = [d1, d2]
    app.active = None
    app.panel = SimpleNamespace(select=lambda d: None, remove=lambda d: None, refresh=lambda d: None)
    app.toolbar = SimpleNamespace(set_editor=lambda e: None)
    app._search_dlg = None
    app.switch_to(d1)
    app._open_search_dialog()
    dlg = app._search_dlg
    dlg._var.set("hello")
    dlg._find_next()
    assert d1.editor.tag_ranges("search_all")  # d1 已高亮
    # insert_plain 的 <<Modified>> 事件延迟触发，close 前显式复位 dirty
    d1.dirty = False
    app.close_doc(d1)  # 关闭活动文档（对话框还开着）
    # 切到 d2 触发 refresh："hello" 不匹配 "world"，不得残留高亮，也不得抛异常
    assert not d2.editor.tag_ranges("search_all")
    dlg._on_close()
    assert not d2.editor.tag_ranges("search_all")  # 关闭对话框清理剩余高亮


def test_find_open_doc_matches_by_realpath(tmp_path):
    # normcase/realpath 判重；path 为 None 的未保存文档不参与
    from app import NoteApp
    f = tmp_path / "a.snote"
    f.write_bytes(b"x")
    app = NoteApp.__new__(NoteApp)
    existing = _FakeDoc(path=str(f))
    app.docs = [existing, _FakeDoc(path=None)]
    assert app._find_open_doc(str(f)) is existing
    assert app._find_open_doc(str(tmp_path / "other.snote")) is None


def test_load_path_builds_doc(monkeypatch):
    # _load_path = load_document + _make_doc，失败原样抛
    from app import NoteApp
    app = NoteApp.__new__(NoteApp)
    made = []
    monkeypatch.setattr(
        "app.snote.load_document", lambda p: ({"format": "snote", "styles": {}, "ops": [], "images": {}}, {})
    )
    monkeypatch.setattr(app, "_make_doc", lambda **kw: made.append(kw) or SimpleNamespace(dirty=True))
    doc = app._load_path("C:/x/a.snote")
    assert doc.dirty is True  # _load_path 返回 _make_doc 的构造结果
    assert made[0]["path"] == "C:/x/a.snote"
    assert made[0]["title"] == "a.snote"
    assert made[0]["document"]["format"] == "snote"
    assert made[0]["blobs"] == {}


def test_load_path_propagates_error(monkeypatch):
    from app import NoteApp
    app = NoteApp.__new__(NoteApp)

    def boom(p):
        raise ValueError("bad")

    monkeypatch.setattr("app.snote.load_document", boom)
    with pytest.raises(ValueError):
        app._load_path("C:/x/a.snote")


def _write_snote(path):
    import snote
    snote.save_document(str(path), snote.build_document({}, [], {}))


def test_open_workspace_loads_nested_snote(tmp_path, monkeypatch):
    # 递归发现子目录中的 .snote，非 .snote 文件忽略，载入后 dirty=False
    from app import NoteApp
    sub = tmp_path / "sub"
    sub.mkdir()
    _write_snote(tmp_path / "a.snote")
    _write_snote(sub / "b.snote")
    (tmp_path / "ignore.txt").write_text("x")
    app = NoteApp.__new__(NoteApp)
    app.docs = []
    added = []
    monkeypatch.setattr("app.filedialog.askdirectory", lambda **k: str(tmp_path))
    monkeypatch.setattr(app, "_make_doc", lambda **kw: SimpleNamespace(path=kw["path"], dirty=True))
    monkeypatch.setattr(app, "add_doc", lambda d: added.append(d))
    monkeypatch.setattr("app.messagebox.showwarning", lambda *a, **k: None)  # 防 bug 时真弹框阻塞
    app.open_workspace()
    got = [os.path.normcase(d.path) for d in added]
    want = [
        os.path.normcase(str(tmp_path / "a.snote")),
        os.path.normcase(str(sub / "b.snote")),
    ]
    assert got == want
    assert all(d.dirty is False for d in added)


def test_open_workspace_skips_already_open(tmp_path, monkeypatch):
    from app import NoteApp
    _write_snote(tmp_path / "a.snote")
    _write_snote(tmp_path / "b.snote")
    app = NoteApp.__new__(NoteApp)
    app.docs = [_FakeDoc(path=str(tmp_path / "a.snote"))]
    added = []
    monkeypatch.setattr("app.filedialog.askdirectory", lambda **k: str(tmp_path))
    monkeypatch.setattr(app, "_make_doc", lambda **kw: SimpleNamespace(path=kw["path"], dirty=True))
    monkeypatch.setattr(app, "add_doc", lambda d: added.append(d))
    monkeypatch.setattr("app.messagebox.showwarning", lambda *a, **k: None)  # 防 bug 时真弹框阻塞
    app.open_workspace()
    assert [os.path.normcase(d.path) for d in added] == [os.path.normcase(str(tmp_path / "b.snote"))]


def test_open_workspace_collects_failures(tmp_path, monkeypatch):
    # 坏文件不阻断其余加载，进入失败汇总弹框
    from app import NoteApp
    _write_snote(tmp_path / "good.snote")
    (tmp_path / "bad.snote").write_bytes(b"not a zip")
    app = NoteApp.__new__(NoteApp)
    app.docs = []
    added = []
    shown = []
    monkeypatch.setattr("app.filedialog.askdirectory", lambda **k: str(tmp_path))
    monkeypatch.setattr(app, "_make_doc", lambda **kw: SimpleNamespace(path=kw["path"], dirty=True))
    monkeypatch.setattr(app, "add_doc", lambda d: added.append(d))
    monkeypatch.setattr("app.messagebox.showwarning", lambda *a, **k: shown.append(a))
    app.open_workspace()
    assert [os.path.normcase(d.path) for d in added] == [os.path.normcase(str(tmp_path / "good.snote"))]
    assert shown and "bad.snote" in str(shown[0])


def test_open_workspace_empty_dir_informs(tmp_path, monkeypatch):
    from app import NoteApp
    app = NoteApp.__new__(NoteApp)
    app.docs = []
    shown = []
    monkeypatch.setattr("app.filedialog.askdirectory", lambda **k: str(tmp_path))
    monkeypatch.setattr("app.messagebox.showinfo", lambda *a, **k: shown.append(a))
    app.open_workspace()
    assert shown


def test_open_workspace_cancel_is_noop(monkeypatch):
    from app import NoteApp
    app = NoteApp.__new__(NoteApp)
    app.docs = []
    monkeypatch.setattr("app.filedialog.askdirectory", lambda **k: "")
    app.open_workspace()  # 不抛、不弹框


def test_open_workspace_failure_list_truncated(tmp_path, monkeypatch):
    # 失败超过 10 条时截断并显示总数
    from app import NoteApp
    for i in range(12):
        (tmp_path / ("bad%d.snote" % i)).write_bytes(b"not a zip")
    app = NoteApp.__new__(NoteApp)
    app.docs = []
    shown = []
    monkeypatch.setattr("app.filedialog.askdirectory", lambda **k: str(tmp_path))
    monkeypatch.setattr("app.messagebox.showwarning", lambda *a, **k: shown.append(a))
    app.open_workspace()
    assert shown
    assert "失败 12 个" in str(shown[0])
    assert "…等 12 个" in str(shown[0])


def test_real_quit_without_listener_cleanup():
    # 监听线程停止已移至 main.py（mainloop 退出路径）；_real_quit 只管 tray -> root
    from app import NoteApp
    app = NoteApp.__new__(NoteApp)
    stopped = []
    app.docs = []
    app._reminder_dlg = None
    app._persist = lambda: None
    app.tray = SimpleNamespace(stop=lambda: stopped.append("tray"))
    app.root = SimpleNamespace(destroy=lambda: stopped.append("root"))
    app._real_quit()
    assert stopped == ["tray", "root"]


def test_noteapp_registers_activation_handler(tk_root, monkeypatch):
    # NoteApp 就绪后注册激活回调：触发时经 tray.enqueue 封送，主线程消费后调 tray.show
    import singleinstance
    import app as appmod

    class _FakeTray:
        def __init__(self, root, on_quit, on_hide):
            self.enqueued = []
            self.shown = 0

        def start(self):
            pass

        def stop(self):
            pass

        def enqueue(self, fn):
            self.enqueued.append(fn)

        def show(self):
            self.shown += 1

        def hide(self):
            pass

        def is_running(self):
            return True

    monkeypatch.setattr(appmod, "TrayController", _FakeTray)
    monkeypatch.setattr(appmod.settings, "save_settings", lambda *a, **k: None)
    monkeypatch.setattr(singleinstance, "_activation_handler", None)  # 防污染
    app = appmod.NoteApp(tk_root)
    try:
        assert singleinstance._activation_handler is not None
        singleinstance._activation_handler()          # 模拟监听线程默认分派（只入队）
        assert len(app.tray.enqueued) == 1
        assert app.tray.shown == 0
        app.tray.enqueued[0]()                        # 模拟主线程 _drain 消费
        assert app.tray.shown == 1
    finally:
        app._real_quit()                              # 清理：停 tray、销毁 root
        singleinstance.set_activation_handler(None)   # 清理模块级回调


def test_menus_and_title_english_in_en_mode(tk_root, monkeypatch):
    # en 模式下主窗口菜单/默认标题为英文；行距显示层翻译、内部值仍为中文键
    import app as appmod

    class _FakeTray:
        def __init__(self, root, on_quit, on_hide):
            pass

        def start(self):
            pass

        def stop(self):
            pass

        def enqueue(self, fn):
            pass

        def show(self):
            pass

        def hide(self):
            pass

        def is_running(self):
            return True

    monkeypatch.setattr(appmod, "TrayController", _FakeTray)
    monkeypatch.setattr(appmod.settings, "save_settings", lambda *a, **k: None)
    saved = lang.get_language()
    lang.set_language("en")
    try:
        app = appmod.NoteApp(tk_root)
        try:
            assert app.docs[0].title == "Untitled"
            menubar = tk_root.nametowidget(tk_root.cget("menu"))
            labels = [menubar.entrycget(i, "label") for i in range(menubar.index("end") + 1)]
            assert labels == ["File", "Edit", "View", "Reminder", "About"]
            view_idx = labels.index("View")
            view_menu = menubar.nametowidget(menubar.entrycget(view_idx, "menu"))
            view_labels = [view_menu.entrycget(i, "label") for i in range(view_menu.index("end") + 1)]
            assert view_labels == ["Compact", "Standard", "Relaxed"]
            assert menubar.entrycget(0, "label") == "File"
            file_menu = menubar.nametowidget(menubar.entrycget(0, "menu"))
            file_labels = [file_menu.entrycget(i, "label") for i in range(file_menu.index("end") + 1)
                           if file_menu.type(i) != "separator"]
            assert file_labels == ["New", "Open", "Open Workspace...", "Save", "Save As", "Quit"]
        finally:
            app._real_quit()
    finally:
        lang.set_language(saved)


def test_noteapp_builds_notebook_tabs_and_loads_todos(tk_root, monkeypatch):
    import app as appmod
    import settings as settingsmod
    from todo_panel import TodoPanel

    class _FakeTray:
        def __init__(self, root, on_quit, on_hide):
            pass

        def start(self):
            pass

        def stop(self):
            pass

        def enqueue(self, fn):
            pass

        def show(self):
            pass

        def hide(self):
            pass

        def is_running(self):
            return True

    data = settingsmod.default_settings()
    data["todos"] = {"items": [{"id": "a", "text": "写周报", "done": False, "pomo": 0}], "current": "a"}
    monkeypatch.setattr(appmod.settings, "load_settings", lambda *a, **k: data)
    monkeypatch.setattr(appmod.settings, "save_settings", lambda *a, **k: None)
    monkeypatch.setattr(appmod, "TrayController", _FakeTray)
    app = appmod.NoteApp(tk_root)
    try:
        assert isinstance(app.sidebar, ttk.Notebook)
        assert list(app.sidebar.tabs()) == [str(app.panel), str(app.todo_panel)]
        assert isinstance(app.todo_panel, TodoPanel)
        assert app.todos.current_id() == "a"
    finally:
        app._real_quit()


def test_tick_adds_pomo_to_current_todo_and_persists(monkeypatch):
    import app as appmod

    t0 = datetime(2026, 8, 22, 9, 0)

    class _FixedDT(datetime):
        @classmethod
        def now(cls):
            return t0 + timedelta(minutes=25)

    sched = reminder.ReminderScheduler()
    sched.update_pomodoro({"work_min": 25, "break_min": 5, "rounds": 4})
    sched.start_pomodoro(t0, task="写周报")
    todos = todo.TodoStore()
    todos.add("写周报")
    todos.set_current(todos.list_items()[0]["id"])
    persisted = []
    refreshed = []
    app = NoteApp.__new__(NoteApp)
    app.scheduler = sched
    app.todos = todos
    app.todo_panel = SimpleNamespace(set_items=lambda *a, **k: refreshed.append(a))
    app._reminder_dlg = None
    app._sound_cfg = {"mode": "system", "path": ""}
    app._title_cache = None
    app.settings = {"todos": todos.to_dict()}
    app.root = SimpleNamespace(after=lambda ms, fn: None, title=lambda s: None)
    monkeypatch.setattr(appmod, "datetime", _FixedDT)
    monkeypatch.setattr(appmod.notify, "notify", lambda *a, **k: None)
    monkeypatch.setattr(appmod.settings, "save_settings", lambda *a, **k: persisted.append(1))
    app._tick()
    assert todos.list_items()[0]["pomo"] == 1   # 计数回写
    assert persisted                             # 同步持久化
    assert refreshed                             # 面板刷新


def test_todo_set_current_updates_scheduler_task():
    t0 = datetime(2026, 8, 22, 9, 0)
    app = NoteApp.__new__(NoteApp)
    app.scheduler = reminder.ReminderScheduler()
    app.todos = todo.TodoStore()
    a = app.todos.add("写周报")
    app.todo_panel = SimpleNamespace(set_items=lambda *a, **k: None)
    app._persist = lambda: None
    app.scheduler.start_pomodoro(t0)
    app._todo_set_current(a["id"])
    assert app.scheduler._pomo_task == "写周报"
    app._todo_set_current(None)
    assert app.scheduler._pomo_task is None


def test_todo_toggle_focus_starts_with_task_and_stops():
    app = NoteApp.__new__(NoteApp)
    app.scheduler = reminder.ReminderScheduler()
    app.todos = todo.TodoStore()
    a = app.todos.add("写周报")
    app.todos.set_current(a["id"])
    app.todo_panel = SimpleNamespace(set_items=lambda *a, **k: None)
    app._title_cache = None
    app.root = SimpleNamespace(title=lambda s: None)
    app._todo_toggle_focus()
    assert app.scheduler.pomodoro_phase() == "work"
    app._todo_toggle_focus()
    assert app.scheduler.pomodoro_phase() == "idle"


def test_todo_toggle_focus_without_current_prompts(monkeypatch):
    shown = []
    monkeypatch.setattr("app.messagebox.showinfo", lambda *a, **k: shown.append(a))
    app = NoteApp.__new__(NoteApp)
    app.scheduler = reminder.ReminderScheduler()
    app.todos = todo.TodoStore()
    app.todo_panel = SimpleNamespace(set_items=lambda *a, **k: None)
    app._title_cache = None
    app.root = SimpleNamespace(title=lambda s: None)
    app._todo_toggle_focus()
    assert shown
    assert app.scheduler.pomodoro_phase() == "idle"


def test_todo_remove_current_while_running_keeps_pomodoro():
    t0 = datetime(2026, 8, 22, 9, 0)
    app = NoteApp.__new__(NoteApp)
    app.scheduler = reminder.ReminderScheduler()
    app.scheduler.start_pomodoro(t0, task="写周报")
    app.todos = todo.TodoStore()
    a = app.todos.add("写周报")
    app.todos.set_current(a["id"])
    app.todo_panel = SimpleNamespace(set_items=lambda *a, **k: None)
    app._persist = lambda: None
    app._todo_remove(a["id"])
    assert app.scheduler.pomodoro_phase() == "work"   # 不中断
    assert app.scheduler._pomo_task is None           # 文案回落
    assert app.todos.current_id() is None
