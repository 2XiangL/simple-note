# 纵向滚动条 + 查找（Ctrl+F）+ 打开工作区 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 为 Simple Note 增加编辑框纵向滚动条、当前笔记浮动查找对话框（Ctrl+F）、以及递归加载目录内所有 `.snote` 的「打开工作区」功能。

**Architecture:** 滚动条采用每文档容器 frame（editor + scrollbar 同生命周期）；查找逻辑分两层——`RichTextEditor` 提供查找原语与高亮 tag，新模块 `search_dialog.py` 提供非模态对话框，经 `editor_provider` 回调取活动编辑器；工作区加载复用从 `open_doc` 抽出的 `_find_open_doc`/`_load_path` 助手，主线程同步批量加载并汇总失败。

**Tech Stack:** Python 3.14、Tkinter（tk.Text / tk.Toplevel / ttk）、pytest（`uv run pytest`），无 lint/typecheck。

**规格来源:** `docs/superpowers/specs/2026-08-03-scrollbar-search-workspace-design.md`

**仓库约定（每个任务都适用）:**
- 新增 UI 字符串与 docstring 一律简体中文
- 验证命令统一为 `uv run pytest`；`tk_root` 用例在无显示器环境静默跳过，核对 skipped 数
- 提交信息沿用仓库风格：`feat(模块): 中文描述`

## File Structure

| 文件 | 动作 | 职责 |
|---|---|---|
| `app.py` | 修改 | 每文档容器 frame；编辑菜单/查找入口；`_find_open_doc`/`_load_path` 助手；`open_workspace` |
| `editor.py` | 修改 | 查找原语：`find_matches`/`search_next`/`search_prev`/`highlight_search`/`clear_search_highlight` + 两个底纹 tag |
| `search_dialog.py` | 新建 | `SearchDialog(tk.Toplevel)` 非模态查找对话框 |
| `tests/test_app.py` | 修改 | 滚动条布线、打开助手、工作区加载（headless 安全 + 1 个 tk_root） |
| `tests/test_editor.py` | 修改 | 查找原语测试（tk_root） |
| `tests/test_search_dialog.py` | 新建 | 对话框行为测试（tk_root） |
| `AGENTS.md` | 修改 | 同步架构与测试清单 |

---

### Task 1: 编辑框纵向滚动条（每文档容器 frame）

**Files:**
- Modify: `app.py:8`（imports）、`app.py:23-28`（NoteDocument）、`app.py:198-209`（_make_doc）、`app.py:284-285`（close_doc）、`app.py:301-305`（switch_to）
- Test: `tests/test_app.py`

- [x] **Step 1: 写失败测试**

在 `tests/test_app.py` 末尾追加：

```python
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
```

- [x] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_app.py::test_make_doc_wires_vertical_scrollbar -v`
Expected: FAIL — `AttributeError: 'NoteDocument' object has no attribute 'frame'`

- [x] **Step 3: 实现容器 frame**

`app.py:8` 导入区，`from tkinter import filedialog, messagebox` 之后加一行：

```python
from tkinter import ttk
```

`app.py:23-28` `NoteDocument.__init__` 改为：

```python
class NoteDocument:
    def __init__(self, frame, editor, path=None, title=None):
        self.frame = frame
        self.editor = editor
        self.path = path
        self.title = title or (Path(path).name if path else "新建笔记")
        self.dirty = False
```

`app.py:198-209` `_make_doc` 改为：

```python
    def _make_doc(self, path=None, title=None, document=None, blobs=None):
        frame = tk.Frame(self.editor_host)
        editor = RichTextEditor(frame)
        sb = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=editor.yview)
        editor.configure(yscrollcommand=sb.set)
        editor.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        editor.set_line_spacing(settings.px_for_level(self._line_spacing))
        doc = NoteDocument(frame, editor, path=path, title=title)
        editor.set_on_dirty(lambda d=doc: self._on_dirty(d))
        if document is not None:
            try:
                editor.from_document(document, blobs or {})
            except Exception:
                editor.destroy()  # 先销毁子控件再销毁容器，保住孤儿控件守卫
                frame.destroy()
                raise
        return doc
```

`app.py:284-285` `close_doc` 中：

```python
        doc.editor.end_resize()
        doc.editor.destroy()
```

改为：

```python
        doc.editor.end_resize()
        doc.frame.destroy()
```

`app.py:301-305` `switch_to` 中：

```python
        if self.active is not None:
            self.active.editor.end_resize()
            self.active.editor.pack_forget()
        self.active = doc
        doc.editor.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
```

改为：

```python
        if self.active is not None:
            self.active.editor.end_resize()
            self.active.frame.pack_forget()
        self.active = doc
        doc.frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
```

- [x] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_app.py -v`
Expected: 全部 PASS（含既有 `test_make_doc_destroys_editor_when_from_document_fails` 与 `test_open_doc_*`）

- [x] **Step 5: 提交**

```bash
git add app.py tests/test_app.py
git commit -m "feat(app): 编辑框每文档容器 frame + 纵向滚动条"
```

---

### Task 2: RichTextEditor 查找原语

**Files:**
- Modify: `editor.py:34`（__init__ 内 tag 配置）、`editor.py:185` 附近（`_on_focus_in` 之后新增「查找」小节）
- Test: `tests/test_editor.py`

- [x] **Step 1: 写失败测试**

在 `tests/test_editor.py` 末尾追加：

```python
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
```

- [x] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_editor.py -k "find_matches or search" -v`
Expected: FAIL — `AttributeError: 'RichTextEditor' object has no attribute 'find_matches'`

- [x] **Step 3: 实现查找原语**

`editor.py` `__init__` 内，`self._widget_font = (family, base_size, "")` 一行（editor.py:34）之后加：

```python
        self.tag_configure("search_all", background="#fff3b0")  # 全部匹配底纹
        self.tag_configure("search_cur", background="#ffd24d")  # 当前匹配底纹
```

`editor.py` 中 `_on_focus_in` 方法（editor.py:181-185）之后、`# ---- 文本插入 ----` 小节之前，新增：

```python
    # ---- 查找 ----
    def find_matches(self, pattern, case):
        """收集全部匹配 [(start, end)]；case=True 区分大小写；空 pattern 返回 []。"""
        if not pattern:
            return []
        matches = []
        pos = "1.0"
        while True:
            pos = self.search(pattern, pos, stopindex=tk.END, nocase=not case)
            if not pos:
                return matches
            end = self.index("%s+%dc" % (pos, len(pattern)))
            matches.append((pos, end))
            pos = end

    def search_next(self, pattern, case):
        """从选区尾（无选区则 insert）向后环绕查找；命中返回 (序号, 总数)，否则 None。"""
        if not pattern:
            self.clear_search_highlight()
            return None
        origin = "sel.last" if self.tag_ranges("sel") else "insert"
        pos = self.search(pattern, origin, stopindex=tk.END, nocase=not case)
        if not pos:
            pos = self.search(pattern, "1.0", stopindex=tk.END, nocase=not case)
        if not pos:
            self.clear_search_highlight()
            return None
        return self._select_match(pos, pattern, case)

    def search_prev(self, pattern, case):
        """从选区头（无选区则 insert）向前环绕查找；命中返回 (序号, 总数)，否则 None。"""
        if not pattern:
            self.clear_search_highlight()
            return None
        origin = "sel.first" if self.tag_ranges("sel") else "insert"
        pos = self.search(pattern, origin, stopindex="1.0", backwards=True, nocase=not case)
        if not pos:
            pos = self.search(pattern, tk.END, stopindex="1.0", backwards=True, nocase=not case)
        if not pos:
            self.clear_search_highlight()
            return None
        return self._select_match(pos, pattern, case)

    def _select_match(self, start, pattern, case):
        end = self.index("%s+%dc" % (start, len(pattern)))
        self.mark_set("insert", start)
        self.tag_remove("sel", "1.0", tk.END)
        self.tag_add("sel", start, end)
        self.see(start)
        self.highlight_search(pattern, case, start)
        matches = self.find_matches(pattern, case)
        current = 0
        for i, (s, _e) in enumerate(matches):
            if self.compare(s, "==", start):
                current = i + 1
                break
        return (current, len(matches))

    def highlight_search(self, pattern, case, current_start=None):
        """刷新查找底纹：search_all 覆盖全部匹配，search_cur 覆盖当前匹配。"""
        self.tag_remove("search_all", "1.0", tk.END)
        self.tag_remove("search_cur", "1.0", tk.END)
        for s, e in self.find_matches(pattern, case):
            self.tag_add("search_all", s, e)
        if current_start is not None:
            self.tag_add("search_cur", current_start, "%s+%dc" % (current_start, len(pattern)))
        self.tag_raise("search_all")
        self.tag_raise("search_cur")  # 后 raise 优先级更高：当前匹配盖住全部匹配

    def clear_search_highlight(self):
        """移除全部查找底纹。"""
        self.tag_remove("search_all", "1.0", tk.END)
        self.tag_remove("search_cur", "1.0", tk.END)
```

- [x] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_editor.py -v`
Expected: 全部 PASS（含既有样式/roundtrip 用例——查找 tag 不得污染样式逻辑）

- [x] **Step 5: 提交**

```bash
git add editor.py tests/test_editor.py
git commit -m "feat(editor): 查找原语 find_matches/search_next/search_prev 与底纹高亮"
```

---

### Task 3: SearchDialog 查找对话框

**Files:**
- Create: `search_dialog.py`
- Test: `tests/test_search_dialog.py`（新建）

- [x] **Step 1: 写失败测试**

新建 `tests/test_search_dialog.py`：

```python
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
```

- [x] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_search_dialog.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'search_dialog'`

- [x] **Step 3: 实现 SearchDialog**

新建 `search_dialog.py`：

```python
"""SearchDialog：查找对话框（非模态 Toplevel）。"""

import tkinter as tk
from tkinter import ttk


class SearchDialog(tk.Toplevel):
    """当前文档查找：经 editor_provider 回调取活动编辑器，自动跟随文档切换。"""

    def __init__(self, master, editor_provider):
        super().__init__(master)
        self.title("查找")
        self._editor_provider = editor_provider
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        bar = ttk.Frame(self, padding=6)
        bar.pack(fill=tk.X)
        self._var = tk.StringVar()
        self._var.trace_add("write", lambda *_: self._on_entry_change())
        self._entry = ttk.Entry(bar, textvariable=self._var, width=24)
        self._entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._entry.bind("<Return>", lambda e: self._find_next())
        self._entry.bind("<Shift-Return>", lambda e: self._find_prev())
        self._entry.bind("<Escape>", lambda e: self._on_close())
        ttk.Button(bar, text="上一个", width=6, command=self._find_prev).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(bar, text="下一个", width=6, command=self._find_next).pack(side=tk.LEFT, padx=(6, 0))
        self._case_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            bar, text="区分大小写", variable=self._case_var, command=self._on_entry_change
        ).pack(side=tk.LEFT, padx=6)
        self._status = ttk.Label(bar, text="")
        self._status.pack(side=tk.LEFT, padx=4)

    def focus_entry(self):
        """聚焦输入框并全选，供重开对话框时调用。"""
        self._entry.focus_set()
        self._entry.select_range(0, tk.END)

    def _editor(self):
        return self._editor_provider()

    def _on_entry_change(self):
        ed = self._editor()
        if ed is None or not ed.winfo_exists():
            return
        pattern = self._var.get()
        if not pattern:
            ed.clear_search_highlight()
            self._set_status("")
            return
        case = self._case_var.get()
        ed.highlight_search(pattern, case, None)
        n = len(ed.find_matches(pattern, case))
        self._set_status("共 %d 处" % n if n else "无匹配")

    def _find_next(self):
        self._step(lambda ed, p, c: ed.search_next(p, c))

    def _find_prev(self):
        self._step(lambda ed, p, c: ed.search_prev(p, c))

    def _step(self, fn):
        ed = self._editor()
        if ed is None or not ed.winfo_exists():
            return
        pattern = self._var.get()
        if not pattern:
            self._set_status("")
            return
        result = fn(ed, pattern, self._case_var.get())
        self._set_status("%d/%d" % result if result else "无匹配")

    def _set_status(self, text):
        self._status.configure(text=text)

    def _on_close(self):
        ed = self._editor()
        if ed is not None and ed.winfo_exists():
            ed.clear_search_highlight()
        self.destroy()
```

- [x] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_search_dialog.py -v`
Expected: 4 个用例全部 PASS

- [x] **Step 5: 提交**

```bash
git add search_dialog.py tests/test_search_dialog.py
git commit -m "feat(ui): 查找对话框 SearchDialog（Enter/Shift+Enter/Esc，区分大小写）"
```

---

### Task 4: app 查找入口（编辑菜单 + Ctrl+F）

**Files:**
- Modify: `app.py:13-18`（imports）、`app.py:56` 附近（`_search_dlg` 初始化）、`app.py:89-122`（_build_menu）
- Test: `tests/test_app.py`

- [x] **Step 1: 写失败测试**

在 `tests/test_app.py` 末尾追加：

```python
def test_open_search_dialog_singleton(tk_root):
    # 对话框单例复用：已存在则 lift，销毁后可重建
    from app import NoteApp
    app = NoteApp.__new__(NoteApp)
    app.root = tk_root
    app.active = None
    app._open_search_dialog()
    first = app._search_dlg
    assert first is not None and first.winfo_exists()
    app._open_search_dialog()
    assert app._search_dlg is first
    first.destroy()
    app._open_search_dialog()
    assert app._search_dlg is not first
```

- [x] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_app.py::test_open_search_dialog_singleton -v`
Expected: FAIL — `AttributeError: 'NoteApp' object has no attribute '_open_search_dialog'`

- [x] **Step 3: 实现入口与菜单**

`app.py` 导入区，`from toolbar import FormatToolbar`（app.py:18）之后加：

```python
from search_dialog import SearchDialog
```

`app.py` `__init__` 中 `self._reminder_dlg = None`（app.py:56）之后加：

```python
        self._search_dlg = None
```

`app.py` `_build_menu` 中，`menubar.add_cascade(label="文件", menu=file_menu)`（app.py:99）之后、「查看」菜单构建之前，插入「编辑」菜单：

```python
        edit_menu = tk.Menu(menubar, tearoff=0)
        edit_menu.add_command(label="查找...", command=self._open_search_dialog, accelerator="Ctrl+F")
        menubar.add_cascade(label="编辑", menu=edit_menu)
```

`app.py` `_build_menu` 末尾的绑定区（app.py:120-122），`<Control-o>` 绑定之后加：

```python
        self.root.bind("<Control-f>", lambda e: self._open_search_dialog())
```

`app.py` `_open_reminder_dialog`（app.py:179-185）之后新增：

```python
    def _open_search_dialog(self):
        if self._search_dlg is not None and self._search_dlg.winfo_exists():
            self._search_dlg.lift()
            self._search_dlg.focus_entry()
            return
        self._search_dlg = SearchDialog(
            self.root, lambda: self.active.editor if self.active is not None else None
        )
        self._search_dlg.focus_entry()
```

- [x] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_app.py -v`
Expected: 全部 PASS

- [x] **Step 5: 提交**

```bash
git add app.py tests/test_app.py
git commit -m "feat(app): Ctrl+F 查找入口与编辑菜单"
```

---

### Task 5: 打开助手抽取（_find_open_doc / _load_path）

**Files:**
- Modify: `app.py:220-242`（open_doc 重构 + 两个助手）
- Test: `tests/test_app.py`

- [x] **Step 1: 写失败测试**

在 `tests/test_app.py` 末尾追加：

```python
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
    assert doc is made[0]
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
```

- [x] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_app.py -k "find_open_doc or load_path" -v`
Expected: FAIL — `AttributeError: 'NoteApp' object has no attribute '_find_open_doc'`

- [x] **Step 3: 抽取助手并重构 open_doc**

`app.py:220-242` 整个 `open_doc` 方法替换为：

```python
    def _find_open_doc(self, path):
        """按 normcase/realpath 判重：返回已打开同一文件的 doc，未打开返回 None。"""
        key = os.path.normcase(os.path.realpath(path))
        for doc in self.docs:
            # doc.path 为 None（未保存）的文档不参与判重
            if doc.path is not None and os.path.normcase(os.path.realpath(doc.path)) == key:
                return doc
        return None

    def _load_path(self, path):
        """从磁盘载入并构造 doc；失败抛异常由调用方处理。"""
        document, blobs = snote.load_document(path)
        return self._make_doc(path=path, title=os.path.basename(path), document=document, blobs=blobs)

    def open_doc(self):
        path = filedialog.askopenfilename(title="打开笔记", filetypes=NOTE_FILTER)
        if not path:
            return
        existing = self._find_open_doc(path)
        if existing is not None:
            self.switch_to(existing)
            return
        try:
            doc = self._load_path(path)
        except Exception as exc:
            messagebox.showerror("打开失败", "无法打开该文件：%s" % exc)
            return
        doc.dirty = False
        self.add_doc(doc)
```

- [x] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_app.py -v`
Expected: 全部 PASS——特别是既有 `test_open_doc_dedupes_already_open_path`、`test_open_doc_dedupes_by_realpath_case`、`test_open_doc_ignores_unsaved_docs_in_dedupe` 保持绿色（重构行为等价）

- [x] **Step 5: 提交**

```bash
git add app.py tests/test_app.py
git commit -m "refactor(app): 抽取 _find_open_doc/_load_path 打开助手"
```

---

### Task 6: 打开工作区（递归加载 .snote）

**Files:**
- Modify: `app.py:93` 附近（文件菜单项）、`app.py:121` 附近（绑定）、`app.py` open_doc 之后（open_workspace）
- Test: `tests/test_app.py`

- [x] **Step 1: 写失败测试**

在 `tests/test_app.py` 末尾追加：

```python
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
    got = sorted(os.path.normcase(d.path) for d in added)
    want = sorted(os.path.normcase(str(p)) for p in (tmp_path / "a.snote", sub / "b.snote"))
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
```

注意：`test_open_workspace_*` 用到 `os`，确认 `tests/test_app.py` 顶部已有 `import os`（既有文件已导入）。

- [x] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_app.py -k "open_workspace" -v`
Expected: FAIL — `AttributeError: 'NoteApp' object has no attribute 'open_workspace'`

- [x] **Step 3: 实现 open_workspace 与菜单项**

`app.py` 中 `open_doc` 方法之后新增：

```python
    def open_workspace(self):
        directory = filedialog.askdirectory(title="打开工作区")
        if not directory:
            return
        files = sorted(Path(directory).rglob("*.snote"), key=lambda p: os.path.normcase(str(p)))
        if not files:
            messagebox.showinfo("打开工作区", "该目录下没有 .snote 笔记文件。")
            return
        loaded = 0
        skipped = 0
        failures = []
        for p in files:
            path = str(p)
            if self._find_open_doc(path) is not None:
                skipped += 1
                continue
            try:
                doc = self._load_path(path)
            except Exception as exc:
                failures.append("%s：%s" % (p.name, exc))
                continue
            doc.dirty = False
            self.add_doc(doc)
            loaded += 1
        if failures:
            lines = failures[:10]
            if len(failures) > 10:
                lines.append("…等 %d 个" % len(failures))
            messagebox.showwarning(
                "打开工作区",
                "已加载 %d 个，跳过重复 %d 个，失败 %d 个：\n%s"
                % (loaded, skipped, len(failures), "\n".join(lines)),
            )
```

`app.py` `_build_menu` 中，「打开」菜单项（`file_menu.add_command(label="打开", ...)`）之后加：

```python
        file_menu.add_command(label="打开工作区...", command=self.open_workspace, accelerator="Ctrl+Shift+O")
```

`app.py` `_build_menu` 末尾绑定区，`<Control-o>` 绑定之后加：

```python
        self.root.bind("<Control-Shift-O>", lambda e: self.open_workspace())
```

- [x] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_app.py -v`
Expected: 全部 PASS

- [x] **Step 5: 提交**

```bash
git add app.py tests/test_app.py
git commit -m "feat(app): 打开工作区——递归加载 .snote，判重跳过、失败汇总"
```

---

### Task 7: 全量验证 + 同步 AGENTS.md

**Files:**
- Modify: `AGENTS.md`

- [x] **Step 1: 跑全量测试**

Run: `uv run pytest -q`
Expected: 全部 PASS；与开工前基线（166 passed, 1 skipped）相比，新增用例全部通过，skipped 数不变（本机有显示器；headless 环境会多出 tk_root 用例的跳过，属预期）

- [x] **Step 2: 手动冒烟（可选，需显示器）**

Run: `uv run python main.py`
验证：① 长文本出现纵向滚动条且滚动同步；② Ctrl+F 弹出查找框，Enter/Shift+Enter 循环定位、底纹正确、Esc 关闭后底纹消失；③ 文件→打开工作区 选择含嵌套 `.snote` 的目录，左侧列表按序加载。

- [x] **Step 3: 更新 AGENTS.md**

`AGENTS.md`「Environment gotchas」中测试清单一条，把：

```
`test_editor`, `test_notes_panel`, and `test_reminder_dialog` need a display.
```

改为：

```
`test_editor`, `test_notes_panel`, `test_reminder_dialog`, and `test_search_dialog` need a display.
```

`AGENTS.md`「Architecture」开头一条（`Entry point is main.py → app.NoteApp ...`）末尾追加：

```
每个文档的 editor 与纵向滚动条同装在一个每文档容器 `tk.Frame`（`NoteDocument.frame`）里，`switch_to`/`close_doc` 以 frame 为单位 pack/destroy。
```

`AGENTS.md`「Architecture」`editor.py` 条目末尾追加：

```
查找原语 `find_matches`/`search_next`/`search_prev`/`highlight_search`/`clear_search_highlight` 只用两个底纹 tag（`search_all`/`search_cur`，仅设 background），不触碰样式 tag；next/prev 分别从 `sel.last`/`sel.first` 起搜并环绕，避免原地重复命中。
```

`AGENTS.md`「Architecture」`reminder_dialog.py` 条目之后新增一条：

```
- `search_dialog.py` — 非模态查找对话框 `SearchDialog(tk.Toplevel)`：构造参数 `editor_provider` 是返回活动 editor 的回调（由 `app.NoteApp._open_search_dialog` 传入），天然跟随文档切换/关闭；文本操作全部委托 editor 查找方法，对话框本身不碰 tk.Text。
```

`AGENTS.md`「Architecture」`snote.py` 条目之后新增一条：

```
- `app.open_workspace` — 「打开工作区」：`askdirectory` + `Path.rglob("*.snote")` 递归批量载入，复用 `_find_open_doc`（判重跳过）/`_load_path`（load + _make_doc）两个助手（`open_doc` 同源）；坏文件收集进失败汇总弹框，不阻断其余加载。全程主线程同步，勿引入后台线程。
```

- [x] **Step 4: 提交**

```bash
git add AGENTS.md
git commit -m "docs(agents): 同步滚动条/查找/打开工作区变更"
```
