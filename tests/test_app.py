import os
import sys
from types import SimpleNamespace

import pytest

import settings


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


def test_load_path_propagates_error(monkeypatch):
    from app import NoteApp
    app = NoteApp.__new__(NoteApp)

    def boom(p):
        raise ValueError("bad")

    monkeypatch.setattr("app.snote.load_document", boom)
    with pytest.raises(ValueError):
        app._load_path("C:/x/a.snote")
