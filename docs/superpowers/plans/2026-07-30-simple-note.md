# Simple Note 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个基于 Tkinter + Pillow 的轻量化本地便签工具，支持富文本（颜色/字号/加粗/斜体/删除线）、剪贴板图片内联粘贴与 8 点缩放、多文档切换，并保存为自包含 `.snote`(zip+JSON) 文件。

**Architecture:** GUI 用标准库 Tkinter（零 GUI 三方依赖），仅引入 Pillow 处理剪贴板取图与图片重采样。富文本采用「复合标签」模型——每种唯一样式组合对应一个 Text tag（内含完整 font），保证加粗+字号可叠加。文件格式为 zip 包：`content.json`（由 `Text.dump()` 产出的 ops 流 + 样式映射 + 图片元数据）加 `images/<id>.png`。可测逻辑（样式纯函数、.snote 序列化、编辑器往返）抽离为纯函数/集成测试；纯 GUI 交互（8 点缩放浮层、工具栏、面板）以手工验收清单覆盖。

**Tech Stack:** Python ≥ 3.14, Tkinter (stdlib), Pillow, pytest。

参考设计：`docs/superpowers/specs/2026-07-30-simple-note-design.md`

---

## 文件结构

| 文件 | 职责 |
|------|------|
| `pyproject.toml` | 声明 Pillow 依赖、pytest dev 依赖 |
| `util.py` | 富文本样式纯函数 + `get_clipboard_image()` |
| `snote.py` | `build_document` / `save_document` / `load_document`（zip+JSON） |
| `editor.py` | `RichTextEditor(tk.Text)`：复合标签、序列化、剪贴板粘贴、双击缩放钩子 |
| `image_resizer.py` | `ImageResizer`：8 点缩放浮层（Canvas `.place()` 覆盖编辑器） |
| `toolbar.py` | `FormatToolbar(ttk.Frame)`：颜色/字号/加粗/斜体/删除线 |
| `notes_panel.py` | `NotesPanel`：左侧笔记列表 + 右键菜单 |
| `app.py` | `NoteDocument` 数据模型 + `NoteApp` 主窗口/菜单/多文档协调/dirty 提示 |
| `main.py` | 入口：建 Tk root、Pillow 检测、mainloop |
| `tests/test_util.py` | 样式纯函数单测 |
| `tests/test_snote.py` | .snote 序列化单测（含图、损坏、往返） |
| `tests/test_editor.py` | 编辑器复合标签 + 往返集成测试（隐藏 Tk root） |
| `tests/conftest.py` | `tk_root` fixture（无显示则 skip） |

---

## Task 1: 项目依赖与测试脚手架

**Files:**
- Modify: `pyproject.toml`
- Modify: `.gitignore`
- Create: `tests/conftest.py`
- Create: `tests/.gitkeep`（如需）

- [ ] **Step 1: 添加 Pillow 与 pytest 依赖**

Run:
```bash
uv add Pillow
uv add --dev pytest
```

预期：`pyproject.toml` 的 `dependencies` 含 `Pillow`，`dev-dependencies` 含 `pytest`，并生成 `uv.lock`。

- [ ] **Step 2: 确认依赖文件内容**

Read `pyproject.toml`，确认形如：
```toml
[project]
name = "simple-note"
version = "0.1.0"
description = "轻量化本地便签工具"
readme = "README.md"
requires-python = ">=3.14"
dependencies = ["pillow>=11.0"]

[dependency-groups]
dev = ["pytest>=8.0"]
```
（版本号以 `uv add` 实际写入为准，不必与示例完全一致。）

- [ ] **Step 3: 在 .gitignore 追加测试/缓存忽略项**

Modify `.gitignore`，在末尾追加：
```
.pytest_cache/
.coverage
```

- [ ] **Step 4: 创建 conftest.py 提供 tk_root fixture**

Create `tests/conftest.py`:
```python
import tkinter as tk

import pytest


@pytest.fixture()
def tk_root():
    try:
        root = tk.Tk()
    except Exception as exc:  # 无显示环境
        pytest.skip("no display for Tk: %s" % exc)
    root.withdraw()
    yield root
    try:
        root.update()
        root.destroy()
    except Exception:
        pass
```

- [ ] **Step 5: 验证 pytest 可运行**

Run:
```bash
uv run pytest -q
```
预期：no tests ran（或 0 passed），无收集错误，无 import 错误。

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock .gitignore tests/conftest.py
git commit -m "chore: add Pillow/pytest deps and test scaffold"
```

---

## Task 2: util.py 样式纯函数（TDD）

**Files:**
- Create: `tests/test_util.py`
- Create: `util.py`

- [ ] **Step 1: 写失败测试**

Create `tests/test_util.py`:
```python
import util


def test_merge_style_overwrites_and_sets():
    assert util.merge_style({"bold": True}, {"size": 20}) == {"bold": True, "size": 20}


def test_merge_style_none_removes_key():
    assert util.merge_style({"bold": True, "size": 20}, {"bold": None}) == {"size": 20}


def test_merge_style_empty_base():
    assert util.merge_style({}, {"italic": True}) == {"italic": True}


def test_style_to_font_basic():
    assert util.style_to_font({}) == ("TkDefaultFont", 12, "")


def test_style_to_font_bold_italic_size():
    assert util.style_to_font({"bold": True, "italic": True, "size": 20}) == (
        "TkDefaultFont",
        20,
        "bold italic",
    )


def test_style_to_tag_config_strike_and_fg():
    cfg = util.style_to_tag_config({"strike": True, "fg": "#ff0000", "size": 14})
    assert cfg["font"] == ("TkDefaultFont", 14, "")
    assert cfg["overstrike"] == 1
    assert cfg["foreground"] == "#ff0000"


def test_style_to_tag_config_no_strike_omits_key():
    cfg = util.style_to_tag_config({"bold": True})
    assert "overstrike" not in cfg
    assert "foreground" not in cfg
    assert cfg["font"] == ("TkDefaultFont", 12, "bold")
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `uv run pytest tests/test_util.py -v`
预期：FAIL（`ModuleNotFoundError: No module named 'util'`）。

- [ ] **Step 3: 实现 util.py 样式纯函数**

Create `util.py`:
```python
"""纯函数：富文本样式逻辑 + 剪贴板图片工具。"""

DEFAULT_FAMILY = "TkDefaultFont"
DEFAULT_SIZE = 12


def merge_style(base, delta):
    """返回 base 合并 delta 后的新样式 dict。

    delta 值为 None 表示删除该键；否则覆盖/新增。
    """
    merged = dict(base)
    for key, value in delta.items():
        if value is None:
            merged.pop(key, None)
        else:
            merged[key] = value
    return merged


def style_to_font(style, family=DEFAULT_FAMILY, base_size=DEFAULT_SIZE):
    """构造 Tk 字体元组 (family, size, flags)。"""
    size = style.get("size", base_size)
    flags = []
    if style.get("bold"):
        flags.append("bold")
    if style.get("italic"):
        flags.append("italic")
    return (family, size, " ".join(flags))


def style_to_tag_config(style, family=DEFAULT_FAMILY, base_size=DEFAULT_SIZE):
    """根据样式 dict 生成 Text.tag_configure 的关键字参数。"""
    config = {"font": style_to_font(style, family, base_size)}
    if style.get("strike"):
        config["overstrike"] = 1
    if "fg" in style:
        config["foreground"] = style["fg"]
    return config
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `uv run pytest tests/test_util.py -v`
预期：7 passed。

- [ ] **Step 5: Commit**

```bash
git add tests/test_util.py util.py
git commit -m "feat: add rich-text style pure functions"
```

---

## Task 3: snote.py —— .snote 文件格式（TDD）

**Files:**
- Create: `tests/test_snote.py`
- Create: `snote.py`

- [ ] **Step 1: 写失败测试**

Create `tests/test_snote.py`:
```python
import json
import zipfile

import pytest

import snote


def _doc():
    styles = {"s1": {"bold": True, "size": 20}}
    ops = [
        {"k": "tagon", "name": "s1"},
        {"k": "text", "text": "Hi"},
        {"k": "tagoff", "name": "s1"},
        {"k": "image", "id": "img1"},
    ]
    images = {"img1": {"file": "images/img1.png", "width": 10, "height": 8}}
    return snote.build_document(styles, ops, images)


def test_build_document_shape():
    doc = _doc()
    assert doc["format"] == "snote"
    assert doc["version"] == 1
    assert doc["ops"][0] == {"k": "tagon", "name": "s1"}


def test_roundtrip_without_images(tmp_path):
    doc = snote.build_document({"s1": {"bold": True}}, [{"k": "text", "text": "x"}], {})
    path = tmp_path / "a.snote"
    snote.save_document(path, doc, {})
    loaded, blobs = snote.load_document(path)
    assert loaded == doc
    assert blobs == {}


def test_roundtrip_with_images(tmp_path):
    doc = _doc()
    path = tmp_path / "b.snote"
    blobs = {"img1": b"PNG-BYTES"}
    snote.save_document(path, doc, blobs)
    loaded, loaded_blobs = snote.load_document(path)
    assert loaded == doc
    assert loaded_blobs == {"img1": b"PNG-BYTES"}


def test_load_bad_zip_raises(tmp_path):
    path = tmp_path / "bad.snote"
    path.write_bytes(b"not a zip")
    with pytest.raises(ValueError):
        snote.load_document(path)


def test_load_missing_content_json_raises(tmp_path):
    path = tmp_path / "nojson.snote"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("other.txt", "x")
    with pytest.raises(ValueError):
        snote.load_document(path)


def test_load_wrong_format_raises(tmp_path):
    path = tmp_path / "wrong.snote"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("content.json", json.dumps({"format": "other", "version": 1}))
    with pytest.raises(ValueError):
        snote.load_document(path)


def test_missing_image_blob_tolerated(tmp_path):
    doc = snote.build_document(
        {}, [{"k": "image", "id": "img1"}], {"img1": {"file": "images/missing.png", "width": 1, "height": 1}}
    )
    path = tmp_path / "c.snote"
    snote.save_document(path, doc, {})  # 不提供 img1 的 bytes
    loaded, blobs = snote.load_document(path)
    assert loaded == doc
    assert blobs == {}
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `uv run pytest tests/test_snote.py -v`
预期：FAIL（`ModuleNotFoundError: No module named 'snote'`）。

- [ ] **Step 3: 实现 snote.py**

Create `snote.py`:
```python
""".snote 自包含文件格式：zip(content.json + images/<id>.png)。"""

import json
import zipfile

FORMAT = "snote"
VERSION = 1


def build_document(styles, ops, images):
    """组装内存中的 document dict。"""
    return {
        "version": VERSION,
        "format": FORMAT,
        "styles": styles,
        "ops": ops,
        "images": images,
    }


def save_document(path, document, image_blobs=None):
    """把 document 写入 .snote(zip)。

    image_blobs: {img_id: 原始 bytes}，仅写入 document['images'] 中引用且提供的图片。
    """
    image_blobs = image_blobs or {}
    with zipfile.ZipFile(str(path), "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("content.json", json.dumps(document, ensure_ascii=False))
        for img_id, meta in document.get("images", {}).items():
            data = image_blobs.get(img_id)
            if data is None:
                continue
            zf.writestr(meta["file"], data)


def load_document(path):
    """读取 .snote，返回 (document, image_blobs)。

    非 .snote/损坏文件抛 ValueError。缺失的图片 bytes 被容忍（不返回）。
    """
    try:
        with zipfile.ZipFile(str(path), "r") as zf:
            if "content.json" not in zf.namelist():
                raise ValueError("missing content.json")
            document = json.loads(zf.read("content.json"))
            names = set(zf.namelist())
            image_blobs = {}
            for img_id, meta in document.get("images", {}).items():
                f = meta.get("file")
                if f and f in names:
                    image_blobs[img_id] = zf.read(f)
    except zipfile.BadZipFile as exc:
        raise ValueError("not a zip / .snote file") from exc

    if document.get("format") != FORMAT:
        raise ValueError("not a .snote document")
    return document, image_blobs
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `uv run pytest tests/test_snote.py -v`
预期：7 passed。

- [ ] **Step 5: Commit**

```bash
git add tests/test_snote.py snote.py
git commit -m "feat: add .snote (zip+JSON) file format"
```

---

## Task 4: util.get_clipboard_image()

**Files:**
- Modify: `util.py`

- [ ] **Step 1: 追加剪贴板取图函数到 util.py**

在 `util.py` 末尾追加：
```python
def get_clipboard_image():
    """从剪贴板获取 PIL.Image，无图或失败返回 None。"""
    try:
        from PIL import ImageGrab
    except Exception:
        return None
    try:
        img = ImageGrab.grabclipboard()
    except Exception:
        return None
    return img
```

- [ ] **Step 2: 冒烟验证 import 不报错**

Run: `uv run python -c "import util; print(util.get_clipboard_image())"`
预期：打印 `None`（剪贴板无图时）或一个 PIL.Image 对象，无异常。

- [ ] **Step 3: Commit**

```bash
git add util.py
git commit -m "feat: add clipboard image helper"
```

---

## Task 5: editor.py —— RichTextEditor 复合标签核心（集成测试）

**Files:**
- Create: `tests/test_editor.py`
- Create: `editor.py`

- [ ] **Step 1: 写失败测试（复合标签应用 + 读取）**

Create `tests/test_editor.py`:
```python
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
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `uv run pytest tests/test_editor.py -v`
预期：FAIL（`ModuleNotFoundError: No module named 'editor'`）。

- [ ] **Step 3: 实现 editor.py 核心**

Create `editor.py`:
```python
"""RichTextEditor：tk.Text 子类，复合标签富文本。"""

import tkinter as tk

import util


class RichTextEditor(tk.Text):
    def __init__(self, master=None, family=util.DEFAULT_FAMILY, base_size=util.DEFAULT_SIZE, **kwargs):
        kwargs.setdefault("font", (family, base_size, ""))
        kwargs.setdefault("wrap", "word")
        kwargs.setdefault("undo", True)
        super().__init__(master, **kwargs)
        self.family = family
        self.base_size = base_size
        self._style_tags = {}        # tag id -> style dict
        self._images = {}            # img id -> {source, photo, width, height}
        self._style_counter = 0
        self._image_counter = 0
        self._current_style = {}
        self._loading = False
        self._on_dirty = None
        self._resizer = None
        self.bind("<KeyRelease>", self._on_cursor_move, add="+")
        self.bind("<ButtonRelease-1>", self._on_cursor_move, add="+")

    # ---- dirty 回调 ----
    def set_on_dirty(self, callback):
        self._on_dirty = callback

    def _mark_dirty(self):
        if self._loading:
            return
        if self._on_dirty:
            self._on_dirty()

    # ---- 样式标签管理 ----
    def _get_or_create_tag(self, style):
        for tag, st in self._style_tags.items():
            if st == style:
                return tag
        self._style_counter += 1
        tag = "s%d" % self._style_counter
        self._style_tags[tag] = dict(style)
        self.tag_configure(tag, **util.style_to_tag_config(style, self.family, self.base_size))
        return tag

    def _style_at(self, index):
        for tag in self.tag_names(index):
            if tag in self._style_tags:
                return dict(self._style_tags[tag])
        return {}

    def _on_cursor_move(self, _event=None):
        before = self.index("insert -1c")
        self._current_style = self._style_at(before)

    # ---- 文本插入（自动套用当前样式）----
    def insert(self, index, chars, *args):
        start = self.index(index)
        super().insert(index, chars, *args)
        if self._loading or not self._current_style:
            self._mark_dirty()
            return
        tag = self._get_or_create_tag(self._current_style)
        end = self.index("%s +%dc" % (start, len(chars)))
        self.tag_add(tag, start, end)
        self._mark_dirty()

    def insert_plain(self, text):
        """供测试/加载使用：插入不带样式的纯文本。"""
        self._loading = True
        try:
            self.insert("end-1c", text)
        finally:
            self._loading = False

    # ---- 对选区应用样式 ----
    def effective_style(self):
        if self.tag_ranges("sel"):
            return self._style_at(self.index("sel.first"))
        return dict(self._current_style)

    def apply_style_to_selection(self, delta):
        if self.tag_ranges("sel"):
            self._apply_delta_range(self.index("sel.first"), self.index("sel.last"), delta)
        else:
            self._current_style = util.merge_style(self._current_style, delta)
            self._mark_dirty()

    def _apply_delta_range(self, start, end, delta):
        idx = start
        while self.compare(idx, "<", end):
            current = self._style_at(idx)
            new_style = util.merge_style(current, delta)
            new_tag = self._get_or_create_tag(new_style)
            for t in list(self.tag_names(idx)):
                if t in self._style_tags:
                    self.tag_remove(t, idx, "%s +1c" % idx)
            self.tag_add(new_tag, idx, "%s +1c" % idx)
            idx = self.index("%s +1c" % idx)
        self._on_cursor_move()
        self._mark_dirty()
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `uv run pytest tests/test_editor.py -v`
预期：3 passed。

- [ ] **Step 5: Commit**

```bash
git add tests/test_editor.py editor.py
git commit -m "feat: add RichTextEditor composite-tag core"
```

---

## Task 6: editor.py —— 序列化与往返（集成测试）

**Files:**
- Modify: `tests/test_editor.py`
- Modify: `editor.py`

- [ ] **Step 1: 追加往返测试**

在 `tests/test_editor.py` 末尾追加：
```python
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
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `uv run pytest tests/test_editor.py -v`
预期：新增 2 个测试 FAIL（`to_document`/`from_document` 不存在）。

- [ ] **Step 3: 实现序列化方法**

在 `editor.py` 的 `RichTextEditor` 类内（`_apply_delta_range` 之后）追加：
```python
    # ---- 序列化 ----
    def to_document(self):
        ops = []
        for kind, value, _index in self.dump("1.0", "end-1c", text=True, tag=True, image=True, mark=False, window=False):
            if kind == "text":
                ops.append({"k": "text", "text": value})
            elif kind == "tagon" and value in self._style_tags:
                ops.append({"k": "tagon", "name": value})
            elif kind == "tagoff" and value in self._style_tags:
                ops.append({"k": "tagoff", "name": value})
            elif kind == "image" and value in self._images:
                ops.append({"k": "image", "id": value})
        used = {op["name"] for op in ops if op["k"] == "tagon"}
        styles = {k: dict(v) for k, v in self._style_tags.items() if k in used}
        images = {
            img_id: {"file": "images/%s.png" % img_id, "width": m["width"], "height": m["height"]}
            for img_id, m in self._images.items()
        }
        import snote
        return snote.build_document(styles, ops, images)

    def get_image_blobs(self):
        import io
        blobs = {}
        for img_id, m in self._images.items():
            buf = io.BytesIO()
            m["source"].save(buf, format="PNG")
            blobs[img_id] = buf.getvalue()
        return blobs

    def from_document(self, document, image_blobs):
        import io
        from PIL import Image as PILImage, ImageTk

        self._loading = True
        try:
            self.delete("1.0", "end")
        finally:
            self._loading = False
        self._style_tags.clear()
        self._images.clear()
        self._style_counter = 0
        self._image_counter = 0

        max_s = 0
        for tag, style in document.get("styles", {}).items():
            self._style_tags[tag] = dict(style)
            self.tag_configure(tag, **util.style_to_tag_config(style, self.family, self.base_size))
            num = tag[1:] if tag.startswith("s") and tag[1:].isdigit() else "0"
            max_s = max(max_s, int(num))
        self._style_counter = max_s

        max_i = 0
        for img_id, meta in document.get("images", {}).items():
            data = image_blobs.get(img_id)
            if data is None:
                continue
            source = PILImage.open(io.BytesIO(data)).convert("RGBA")
            w, h = meta["width"], meta["height"]
            photo = self._make_photo(source, w, h)
            self._images[img_id] = {"source": source, "photo": photo, "width": w, "height": h}
            num = img_id[3:] if img_id.startswith("img") and img_id[3:].isdigit() else "0"
            max_i = max(max_i, int(num))
        self._image_counter = max_i

        self._loading = True
        try:
            active = set()
            for op in document.get("ops", []):
                k = op["k"]
                if k == "tagon":
                    active.add(op["name"])
                elif k == "tagoff":
                    active.discard(op["name"])
                elif k == "text":
                    start = self.index("end-1c")
                    super().insert("end-1c", op["text"])
                    end = self.index("end-1c")
                    for t in active:
                        if t in self._style_tags:
                            self.tag_add(t, start, end)
                elif k == "image":
                    img_id = op["id"]
                    if img_id in self._images:
                        self.image_create("end-1c", name=img_id, image=self._images[img_id]["photo"])
        finally:
            self._loading = False
        self._current_style = {}
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `uv run pytest tests/test_editor.py -v`
预期：5 passed。

- [ ] **Step 5: Commit**

```bash
git add tests/test_editor.py editor.py
git commit -m "feat: add editor document serialization and round-trip"
```

---

## Task 7: editor.py —— 剪贴板粘贴 + 双击缩放钩子

**Files:**
- Modify: `editor.py`

- [ ] **Step 1: 追加图片辅助方法与事件绑定**

在 `editor.py` 的 `RichTextEditor` 类内（`from_document` 之后）追加，并在 `__init__` 内补一行绑定：

先在 `__init__` 末尾（已有两行 bind 之后）追加：
```python
        self.bind("<Control-v>", self._on_paste, add="+")
        self.bind("<Double-Button-1>", self._on_double_click, add="+")
```

再在类内追加方法：
```python
    # ---- 图片 ----
    def _make_photo(self, source, width, height):
        from PIL import Image as PILImage, ImageTk
        resized = source.resize((int(width), int(height)), PILImage.LANCZOS)
        return ImageTk.PhotoImage(resized)

    def insert_image(self, pil_image, max_width=None):
        source = pil_image.copy()
        width, height = source.size
        if max_width and width > max_width:
            height = int(height * (max_width / width))
            width = max_width
        self._image_counter += 1
        img_id = "img%d" % self._image_counter
        photo = self._make_photo(source, width, height)
        self._images[img_id] = {"source": source, "photo": photo, "width": width, "height": height}
        self.image_create("insert", name=img_id, image=photo)
        self._mark_dirty()
        return img_id

    def _index_of_image(self, img_id):
        for kind, value, index in self.dump("1.0", "end", image=True, text=False, tag=False):
            if kind == "image" and value == img_id:
                return index
        return None

    def set_image_size(self, img_id, width, height):
        meta = self._images.get(img_id)
        if not meta:
            return
        meta["photo"] = self._make_photo(meta["source"], width, height)
        meta["width"], meta["height"] = int(width), int(height)
        idx = self._index_of_image(img_id)
        if idx is not None:
            self.image_configure(idx, image=meta["photo"])
        self._mark_dirty()

    def image_display_size(self, img_id):
        meta = self._images.get(img_id)
        if not meta:
            return None
        return meta["width"], meta["height"]

    def image_source(self, img_id):
        meta = self._images.get(img_id)
        return meta["source"] if meta else None

    # ---- 事件 ----
    def _on_paste(self, _event=None):
        img = util.get_clipboard_image()
        if img is None:
            return
        max_width = max(64, self.winfo_width() - 12)
        self.insert_image(img, max_width=max_width)

    def _on_double_click(self, event):
        idx = self.index("@%d,%d" % (event.x, event.y))
        for kind, value, index in self.dump("1.0", "end", image=True, text=False, tag=False):
            if kind == "image" and self.compare(index, "==", idx):
                self.begin_resize(value)
                return "break"

    def begin_resize(self, img_id):
        if self._resizer is not None:
            self._resizer.destroy()
            self._resizer = None
        idx = self._index_of_image(img_id)
        if idx is None:
            return
        bbox = self.bbox(idx)
        if not bbox:
            return
        from image_resizer import ImageResizer
        self._resizer = ImageResizer(self, img_id, bbox)

    def end_resize(self):
        if self._resizer is not None:
            self._resizer.destroy()
            self._resizer = None
```

- [ ] **Step 2: 运行全部测试确认无回归**

Run: `uv run pytest -q`
预期：全部 passed（无回归）。

- [ ] **Step 3: Commit**

```bash
git add editor.py
git commit -m "feat: add clipboard paste and image resize hook in editor"
```

---

## Task 8: image_resizer.py —— 8 点缩放浮层

**Files:**
- Create: `image_resizer.py`

- [ ] **Step 1: 实现 ImageResizer**

Create `image_resizer.py`:
```python
"""ImageResizer：双击图片后的 8 点缩放浮层。"""

import tkinter as tk

HANDLE_SIZE = 8
MIN_SIZE = 16

# 手柄角色（顺时针）
_ROLES = ("nw", "n", "ne", "e", "se", "s", "sw", "w")


class ImageResizer:
    def __init__(self, editor, img_id, bbox):
        self.editor = editor
        self.img_id = img_id
        self.x, self.y, self.orig_w, self.orig_h = bbox
        w, h = editor.image_display_size(img_id)
        self.ratio = (w or 1) / (h or 1)
        self.start_w, self.start_h = w, h
        self._drag_role = None
        self._drag_start = None

        self.canvas = tk.Canvas(editor, highlightthickness=0, bd=0)
        self.canvas.configure(bg="")
        self._draw()
        self._place()

        self.canvas.focus_set()
        self.canvas.bind("<B1-Motion>", self._on_motion)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Return>", lambda e: self._confirm())
        self.canvas.bind("<Escape>", lambda e: self._cancel())
        editor.bind("<Configure>", self._on_editor_changed, add="+")

    # ---- 绘制 ----
    def _draw(self):
        self.canvas.delete("all")
        w, h = self.start_w, self.start_h
        self.canvas.configure(width=w, height=h)
        self.canvas.create_rectangle(1, 1, w - 1, h - 1, outline="#1a73e8", width=2, tags="border")
        self._handles = {}
        for role in _ROLES:
            cx, cy = self._handle_pos(role, w, h)
            hid = self.canvas.create_rectangle(
                cx - HANDLE_SIZE, cy - HANDLE_SIZE, cx + HANDLE_SIZE, cy + HANDLE_SIZE,
                fill="#1a73e8", outline="white", tags=("handle", role),
            )
            self.canvas.tag_bind(hid, "<Button-1>", lambda e, r=role: self._on_handle_press(r, e))
            self._handles[role] = hid

    def _handle_pos(self, role, w, h):
        positions = {
            "nw": (0, 0), "n": (w / 2, 0), "ne": (w, 0),
            "e": (w, h / 2), "se": (w, h), "s": (w / 2, h),
            "sw": (0, h), "w": (0, h / 2),
        }
        return positions[role]

    def _place(self):
        self.canvas.place(x=self.x, y=self.y)

    # ---- 拖拽 ----
    def _on_handle_press(self, role, event):
        self._drag_role = role
        self._drag_start = (event.x_root, event.y_root)
        self.start_w, self.start_h = self.editor.image_display_size(self.img_id)

    def _on_motion(self, event):
        if not self._drag_role or not self._drag_start:
            return
        dx = event.x_root - self._drag_start[0]
        dy = event.y_root - self._drag_start[1]
        role = self._drag_role
        w, h = self.start_w, self.start_h
        if role == "e":
            w = self.start_w + dx
        elif role == "w":
            w = self.start_w - dx
        elif role == "s":
            h = self.start_h + dy
        elif role == "n":
            h = self.start_h - dy
        else:  # 角手柄：锁纵横比
            if role in ("nw", "sw"):
                w = self.start_w - dx
            else:
                w = self.start_w + dx
            h = w / self.ratio
        w = max(MIN_SIZE, int(w))
        h = max(MIN_SIZE, int(h))
        self.editor.set_image_size(self.img_id, w, h)
        self._reposition()

    def _on_release(self, _event):
        self._drag_role = None
        self._drag_start = None

    def _reposition(self):
        idx = self.editor._index_of_image(self.img_id)
        if idx is None:
            return
        bbox = self.editor.bbox(idx)
        if not bbox:
            return
        self.x, self.y, _, _ = bbox
        self.start_w, self.start_h = self.editor.image_display_size(self.img_id)
        self._draw()
        self._place()

    def _on_editor_changed(self, _event=None):
        if self._drag_role:
            return
        self._reposition()

    # ---- 结束 ----
    def _confirm(self):
        self.editor.end_resize()

    def _cancel(self):
        self.editor.set_image_size(self.img_id, int(self.orig_w), int(self.orig_h))
        self.editor.end_resize()

    def destroy(self):
        try:
            self.editor.unbind("<Configure>")
        except Exception:
            pass
        self.canvas.destroy()
```

- [ ] **Step 2: 冒烟 import**

Run: `uv run python -c "import image_resizer; print('ok')"`
预期：打印 `ok`。

- [ ] **Step 3: Commit**

```bash
git add image_resizer.py
git commit -m "feat: add 8-handle image resize overlay"
```

---

## Task 9: toolbar.py —— 格式工具栏

**Files:**
- Create: `toolbar.py`

- [ ] **Step 1: 实现 FormatToolbar**

Create `toolbar.py`:
```python
"""FormatToolbar：颜色/字号/加粗/斜体/删除线。"""

import tkinter as tk
from tkinter import colorchooser, ttk


class FormatToolbar(ttk.Frame):
    def __init__(self, master=None):
        super().__init__(master)
        self.editor = None
        self._build()

    def _build(self):
        self.color_btn = ttk.Button(self, text="颜色", width=6, command=self.on_color)
        self.color_btn.pack(side=tk.LEFT, padx=2, pady=2)

        self.size_var = tk.StringVar(value="12")
        self.size_box = ttk.Combobox(
            self, textvariable=self.size_var, width=4, values=[str(s) for s in range(8, 73, 2)]
        )
        self.size_box.bind("<<ComboboxSelected>>", lambda e: self.on_size())
        self.size_box.bind("<Return>", lambda e: self.on_size())
        self.size_box.pack(side=tk.LEFT, padx=2)

        self.bold_btn = ttk.Button(self, text="B", width=3, command=lambda: self.toggle("bold"))
        self.bold_btn.pack(side=tk.LEFT, padx=2)
        self.italic_btn = ttk.Button(self, text="I", width=3, command=lambda: self.toggle("italic"))
        self.italic_btn.pack(side=tk.LEFT, padx=2)
        self.strike_btn = ttk.Button(self, text="S", width=3, command=lambda: self.toggle("strike"))
        self.strike_btn.pack(side=tk.LEFT, padx=2)

    def set_editor(self, editor):
        self.editor = editor

    def on_color(self):
        if not self.editor:
            return
        _, hexcolor = colorchooser.askcolor(title="选择颜色")
        if hexcolor:
            self.editor.apply_style_to_selection({"fg": hexcolor})

    def on_size(self):
        if not self.editor:
            return
        try:
            size = int(self.size_var.get())
        except ValueError:
            return
        self.editor.apply_style_to_selection({"size": size})

    def toggle(self, attr):
        if not self.editor:
            return
        current = self.editor.effective_style()
        self.editor.apply_style_to_selection({attr: not current.get(attr, False)})
```

- [ ] **Step 2: 冒烟 import**

Run: `uv run python -c "import toolbar; print('ok')"`
预期：打印 `ok`。

- [ ] **Step 3: Commit**

```bash
git add toolbar.py
git commit -m "feat: add format toolbar"
```

---

## Task 10: notes_panel.py —— 笔记栏

**Files:**
- Create: `notes_panel.py`

- [ ] **Step 1: 实现 NotesPanel**

Create `notes_panel.py`:
```python
"""NotesPanel：左侧笔记列表 + 右键菜单。"""

import tkinter as tk
from tkinter import ttk


class NotesPanel(ttk.Frame):
    def __init__(self, master=None, on_switch=None, on_save=None, on_save_as=None, on_close=None):
        super().__init__(master, takefocus=True)
        self.on_switch = on_switch
        self.on_save = on_save
        self.on_save_as = on_save_as
        self.on_close = on_close
        self._docs = []          # 与 listbox 一一对应

        self.listbox = tk.Listbox(self, activestyle="dotbox")
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.listbox.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.listbox.configure(yscrollcommand=sb.set)

        self.listbox.bind("<<ListboxSelect>>", self._on_select)
        self.listbox.bind("<Button-3>", self._on_right_click)

        self.menu = tk.Menu(self, tearoff=0)
        self.menu.add_command(label="保存", command=self._menu_save)
        self.menu.add_command(label="另存为", command=self._menu_save_as)
        self.menu.add_separator()
        self.menu.add_command(label="关闭", command=self._menu_close)

    def add(self, doc):
        self._docs.append(doc)
        self.listbox.insert(tk.END, doc.display_title)
        self.select(doc)

    def remove(self, doc):
        try:
            idx = self._docs.index(doc)
        except ValueError:
            return
        self._docs.pop(idx)
        self.listbox.delete(idx)
        if self._docs:
            self.listbox.selection_set(0)

    def refresh(self, doc):
        try:
            idx = self._docs.index(doc)
        except ValueError:
            return
        self.listbox.delete(idx)
        self.listbox.insert(idx, doc.display_title)

    def select(self, doc):
        try:
            idx = self._docs.index(doc)
        except ValueError:
            return
        self.listbox.selection_clear(0, tk.END)
        self.listbox.selection_set(idx)
        self.listbox.activate(idx)

    def selected_doc(self):
        sel = self.listbox.curselection()
        if not sel:
            return None
        return self._docs[sel[0]]

    def _on_select(self, _event):
        doc = self.selected_doc()
        if doc and self.on_switch:
            self.on_switch(doc)

    def _on_right_click(self, event):
        idx = self.listbox.nearest(event.y)
        if idx < 0 or idx >= len(self._docs):
            return
        self.listbox.selection_clear(0, tk.END)
        self.listbox.selection_set(idx)
        self.menu.tk_popup(event.x_root, event.y_root)

    def _menu_save(self):
        doc = self.selected_doc()
        if doc and self.on_save:
            self.on_save(doc)

    def _menu_save_as(self):
        doc = self.selected_doc()
        if doc and self.on_save_as:
            self.on_save_as(doc)

    def _menu_close(self):
        doc = self.selected_doc()
        if doc and self.on_close:
            self.on_close(doc)
```

- [ ] **Step 2: 冒烟 import**

Run: `uv run python -c "import notes_panel; print('ok')"`
预期：打印 `ok`。

- [ ] **Step 3: Commit**

```bash
git add notes_panel.py
git commit -m "feat: add notes panel with context menu"
```

---

## Task 11: app.py —— NoteDocument + NoteApp 主窗口

**Files:**
- Create: `app.py`

- [ ] **Step 1: 实现 NoteDocument 与 NoteApp**

Create `app.py`:
```python
"""NoteApp：主窗口、菜单、多文档协调。"""

import os
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

import snote
from editor import RichTextEditor
from notes_panel import NotesPanel
from toolbar import FormatToolbar

NOTE_FILTER = [("Simple Note", "*.snote"), ("所有文件", "*.*")]


class NoteDocument:
    def __init__(self, editor, path=None, title=None):
        self.editor = editor
        self.path = path
        self.title = title or (Path(path).name if path else "新建笔记")
        self.dirty = False

    def mark_dirty(self):
        was = self.dirty
        self.dirty = True
        return not was

    @property
    def display_title(self):
        return ("*" if self.dirty else "") + self.title


class NoteApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Simple Note")
        self.root.geometry("900x600")
        self.docs = []
        self.active = None

        self._build_menu()
        self.toolbar = FormatToolbar(root)
        self.toolbar.pack(side=tk.TOP, fill=tk.X)
        self.body = tk.PanedWindow(root, orient=tk.HORIZONTAL)
        self.body.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self.panel = NotesPanel(
            self.body,
            on_switch=self.switch_to,
            on_save=lambda d: self.save(d),
            on_save_as=lambda d: self.save_as(d),
            on_close=lambda d: self.close_doc(d),
        )
        self.body.add(self.panel, minsize=150, width=180)

        self.editor_host = tk.Frame(self.body)
        self.body.add(self.editor_host, minsize=300)

        self.root.protocol("WM_DELETE_WINDOW", self.on_exit)
        self.new_doc()

    # ---- 菜单 ----
    def _build_menu(self):
        menubar = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="新建", command=self.new_doc, accelerator="Ctrl+N")
        file_menu.add_command(label="打开", command=self.open_doc, accelerator="Ctrl+O")
        file_menu.add_separator()
        file_menu.add_command(label="保存", command=lambda: self.save(self.active), accelerator="Ctrl+S")
        file_menu.add_command(label="另存为", command=lambda: self.save_as(self.active))
        file_menu.add_separator()
        file_menu.add_command(label="退出", command=self.on_exit)
        menubar.add_cascade(label="文件", menu=file_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="关于程序", command=self.about)
        menubar.add_cascade(label="关于", menu=help_menu)
        self.root.configure(menu=menubar)

        self.root.bind("<Control-n>", lambda e: self.new_doc())
        self.root.bind("<Control-o>", lambda e: self.open_doc())
        self.root.bind("<Control-s>", lambda e: self.save(self.active))

    # ---- 文档生命周期 ----
    def _make_doc(self, path=None, title=None, document=None, blobs=None):
        editor = RichTextEditor(self.editor_host)
        doc = NoteDocument(editor, path=path, title=title)
        editor.set_on_dirty(lambda d=doc: self._on_dirty(d))
        if document is not None:
            editor.from_document(document, blobs or {})
        return doc

    def add_doc(self, doc):
        self.docs.append(doc)
        self.panel.add(doc)
        self.switch_to(doc)

    def new_doc(self):
        doc = self._make_doc()
        self.add_doc(doc)

    def open_doc(self):
        path = filedialog.askopenfilename(title="打开笔记", filetypes=NOTE_FILTER)
        if not path:
            return
        try:
            document, blobs = snote.load_document(path)
        except ValueError as exc:
            messagebox.showerror("打开失败", "无法打开该文件：%s" % exc)
            return
        title = os.path.basename(path)
        doc = self._make_doc(path=path, title=title, document=document, blobs=blobs)
        doc.dirty = False
        self.add_doc(doc)

    def save(self, doc):
        if doc is None:
            return
        if not doc.path:
            self.save_as(doc)
            return
        try:
            document = doc.editor.to_document()
            blobs = doc.editor.get_image_blobs()
            snote.save_document(doc.path, document, blobs)
        except OSError as exc:
            messagebox.showerror("保存失败", "写入失败：%s" % exc)
            return
        doc.dirty = False
        self.panel.refresh(doc)

    def save_as(self, doc):
        if doc is None:
            return
        path = filedialog.asksaveasfilename(
            title="另存为", defaultextension=".snote", filetypes=NOTE_FILTER
        )
        if not path:
            return
        doc.path = path
        doc.title = os.path.basename(path)
        self.save(doc)

    def close_doc(self, doc):
        if doc is None:
            return
        if doc.dirty and not self._confirm_save(doc):
            return
        if doc.editor is not None:
            if doc.editor._resizer is not None:
                doc.editor.end_resize()
            doc.editor.destroy()
        idx = self.docs.index(doc)
        self.docs.remove(doc)
        self.panel.remove(doc)
        if not self.docs:
            self.new_doc()
            return
        if self.active is doc:
            nxt = self.docs[min(idx, len(self.docs) - 1)]
            self.switch_to(nxt)

    def switch_to(self, doc):
        if doc is None:
            return
        if self.active is doc:
            return
        if self.active is not None and self.active.editor is not None:
            if self.active.editor._resizer is not None:
                self.active.editor.end_resize()
            self.active.editor.pack_forget()
        self.active = doc
        doc.editor.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        doc.editor.focus_set()
        self.toolbar.set_editor(doc.editor)

    def _on_dirty(self, doc):
        if doc is None:
            return
        if doc.mark_dirty():
            self.panel.refresh(doc)

    # ---- 退出/提示 ----
    def _confirm_save(self, doc):
        ans = messagebox.askyesnocancel(
            "Simple Note", "“%s”未保存，是否保存？" % doc.title
        )
        if ans is None:
            return False
        if ans:
            self.save(doc)
        return True

    def on_exit(self):
        for doc in list(self.docs):
            if doc.dirty:
                self.switch_to(doc)
                if not self._confirm_save(doc):
                    return
        self.root.destroy()

    def about(self):
        messagebox.showinfo("关于 Simple Note", "Simple Note\n轻量化本地便签工具\nTkinter + Pillow")


def _doc_ref_holder():
    pass
```

> 说明：`_make_doc` 先创建 `doc` 再用闭包 `lambda d=doc: self._on_dirty(d)` 绑定到编辑器，确保编辑器触发 dirty 时刷新对应面板条目（编辑器内部 `_mark_dirty` 调用 `set_on_dirty` 设置的回调）。

- [ ] **Step 2: 冒烟 import**

Run: `uv run python -c "import app; print('ok')"`
预期：打印 `ok`。

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "feat: add NoteApp main window, menus, multi-doc coordination"
```

---

## Task 12: main.py —— 入口

**Files:**
- Modify: `main.py`

- [ ] **Step 1: 重写 main.py**

Replace `main.py` content with:
```python
"""Simple Note 入口。"""

import tkinter as tk
from tkinter import messagebox


def main():
    try:
        from PIL import Image  # noqa: F401
    except Exception:
        root = tk.Tk()
        root.withdraw()
        messagebox.showwarning("Simple Note", "未检测到 Pillow，图片粘贴/缩放功能将不可用。")
        root.destroy()

    root = tk.Tk()
    from app import NoteApp
    NoteApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 启动应用冒烟**

Run: `uv run python main.py`
预期：窗口打开，菜单/工具栏/左侧笔记栏/编辑区可见；可输入文字、用工具栏改样式；关闭窗口正常退出。若无显示环境则跳过（人工验收）。

- [ ] **Step 3: Commit**

```bash
git add main.py
git commit -m "feat: add application entry point"
```

---

## Task 13: 完整自动化测试 + 手工验收

**Files:**
- 无新增（验证）

- [ ] **Step 1: 运行全部自动化测试**

Run: `uv run pytest -v`
预期：全部 passed（util 7 + snote 7 + editor 5 = 19 passed；编辑器测试在无显示环境自动 skip）。

- [ ] **Step 2: 执行手工验收清单**

启动 `uv run python main.py`，逐项核对（参考设计文档 §11.2）：

1. 新建 → 输入文字 → 分别点 B/I/S/颜色/字号，样式实时生效。
2. 选中已有文本再点工具栏按钮：样式正确合并（如已加粗再改字号，加粗仍保留）。
3. 截屏后 `Ctrl+V` 在光标处内联插入图片。
4. 双击图片出现 8 个手柄；拖角手柄锁纵横比、拖边手柄单方向；`Enter` 确认、`Esc` 恢复。
5. 保存为 `.snote` → 关闭该笔记 → 重新打开，文字/样式/图片/尺寸全部还原。
6. 打开多个笔记，左栏点击切换、右键「保存/另存为/关闭」均可用，未保存时退出有提示。

- [ ] **Step 3: 最终 commit（如有验收中产生的修复）**

```bash
git add -A
git commit -m "test: full suite green + manual acceptance passed"
```
（若验收无改动，此步可跳过。）

---

## Self-Review（计划完成后自检）

**Spec 覆盖：**
- 富文本颜色/字号/加粗/斜体/删除线 → Task 2（纯函数）+ Task 5（应用）+ Task 9（工具栏）✓
- 复合标签可叠加 → Task 2/5 + 测试 `test_merge_size_with_bold` ✓
- 剪贴板粘贴内联图片 → Task 4（取图）+ Task 7（粘贴）✓
- 双击 8 点缩放（角锁比/边自由/Esc 取消/Enter 确认）→ Task 7（钩子）+ Task 8（浮层）✓
- 文件菜单 新建/打开/保存/另存为/退出、关于 → Task 11 ✓
- 自包含 .snote（文本+图片+样式）→ Task 3 + Task 6 ✓
- 左侧笔记栏切换 + 右键 保存/另存/关闭 → Task 10 + Task 11 ✓
- dirty 追踪 + 退出提示 → Task 11 ✓
- 错误处理（损坏文件、缺图、保存失败、Pillow 缺失、缩放中切换）→ Task 3/6/11/12 + Task 11 `close_doc` ✓
- 测试策略（纯逻辑单测 + 手工验收）→ Task 2/3/6 + Task 13 ✓

**Placeholder 扫描：** 无 TBD/TODO；所有代码步骤含完整代码；命令含预期输出 ✓

**类型/命名一致性：** `apply_style_to_selection`、`effective_style`、`to_document`/`from_document`、`get_image_blobs`、`set_image_size`、`image_display_size`、`_index_of_image`、`begin_resize`/`end_resize`、`set_on_dirty`、`display_title`、`NoteDocument.mark_dirty` 在 editor/toolbar/app 间一致 ✓
