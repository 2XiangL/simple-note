# 字号行为 / 图片删除 / 托盘热键 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复无选区切换字号后输入不生效的问题并让字号框随光标自动刷新；为缩放浮层加 Del 删除图片；加 Ctrl+Alt+N 全局热键 + 系统托盘最小化。

**Architecture:** 三项互相独立的增强。Feature A 改 `editor.py`+`toolbar.py`（pending 标志 + cursor-style 回调）；Feature B 改 `editor.py`+`image_resizer.py`；Feature C 新增 `tray.py` 并接线 `app.py`。托盘/热键外部线程回调一律经 `root.after(0, fn)` 派发回 Tk 主线程。

**Tech Stack:** Python 3.14、Tkinter、Pillow；新增 pystray（托盘）、keyboard（全局热键）。测试用 pytest + 真实 Tk（`tk_root` fixture，无显示时跳过）。

**Spec:** `docs/superpowers/specs/2026-07-30-font-size-image-delete-tray-design.md`

**测试运行约定：**
- 全量：`uv run pytest`
- 单测：`uv run pytest tests/test_editor.py::test_xxx`
- 注意看 "skipped" 计数：无显示环境时 `tk_root` 用例静默跳过；纯逻辑用例（test_tray 的状态机、make_icon_image）不依赖显示，必须真正通过。

---

## File Structure

- **改 `editor.py`** — pending 标志（`_pending`）、cursor-style 回调（`_on_cursor_style` + `set_on_cursor_style`）、`delete_image(img_id)`。
- **改 `toolbar.py`** — `_refresh_size(style)` + `set_editor` 注册回调；新增 `import util`。
- **改 `image_resizer.py`** — `<Delete>`/`<Backspace>` 绑定 + `_delete()`。
- **改 `app.py`** — 构造并启动 `TrayController`；`WM_DELETE_WINDOW` 改为最小化到托盘；`on_exit` 重命名为 `_real_quit` 并先 `tray.stop()`。
- **改 `pyproject.toml`** — 加 `pystray`、`keyboard` 依赖。
- **新 `tray.py`** — `make_icon_image()` + `TrayController`（状态机 + 线程派发）。
- **新 `tests/test_tray.py`** — 图标生成 + 状态机（fake root，不起真实托盘）。
- **扩 `tests/test_editor.py`** — pending、delete_image、cursor 回调、字号框刷新用例。

不动：`main.py`、`util.py`、`notes_panel.py`、`snote.py`。

---

## Task 1: 字号 pending 标志（editor.py）

无选区设字号后，pending 保护 `_current_style` 不被光标移动覆盖；输入一个字符后消耗。

**Files:**
- Modify: `editor.py`（`__init__`、`apply_style_to_selection`、`_on_cursor_move`、`insert`）
- Test: `tests/test_editor.py`

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_editor.py` 末尾：

```python
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
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_editor.py::test_pending_style_survives_cursor_move tests/test_editor.py::test_pending_cleared_by_insert -v`
Expected: FAIL（`_pending` 属性不存在 / AttributeError）

- [ ] **Step 3: 实现**

`editor.py` 的 `__init__` 中，在 `self._current_style = {}` 这一行下方追加两行：

```python
        self._current_style = {}
        self._pending = False
        self._on_cursor_style = None
```

把 `_on_cursor_move` 整体替换为：

```python
    def _on_cursor_move(self, _event=None):
        if not self._pending:
            before = self.index("insert -1c")
            self._current_style = self._style_at(before)
        if self._on_cursor_style:
            self._on_cursor_style(dict(self._current_style))
```

把 `apply_style_to_selection` 整体替换为：

```python
    def apply_style_to_selection(self, delta):
        if self.tag_ranges("sel"):
            self._apply_delta_range(self.index("sel.first"), self.index("sel.last"), delta)
        else:
            self._current_style = util.merge_style(self._current_style, delta)
            self._pending = True
            self._mark_dirty()
```

把 `insert` 整体替换为：

```python
    def insert(self, index, chars, *args):
        start = self.index(index)
        super().insert(index, chars, *args)
        if self._loading:
            self._mark_dirty()
            return
        if self._current_style:
            tag = self._get_or_create_tag(self._current_style)
            end = self.index("%s +%dc" % (start, len(chars)))
            self.tag_add(tag, start, end)
        self._pending = False
        self._mark_dirty()
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_editor.py -v`
Expected: PASS（含原有用例 + 2 个新用例，注意 skipped 计数应仅来自无显示环境）

- [ ] **Step 5: 提交**

```bash
git add editor.py tests/test_editor.py
git commit -m "feat: sticky pending style for no-selection toolbar changes"
```

---

## Task 2: cursor-style 回调机制（editor.py）

editor 在光标移动时通知外部（工具栏）当前生效样式，供字号框刷新。

**Files:**
- Modify: `editor.py`（新增 `set_on_cursor_style`，回调已在 Task 1 的 `_on_cursor_move` 里调用）
- Test: `tests/test_editor.py`

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_editor.py` 末尾：

```python
def test_cursor_style_callback_fires_with_current_style(tk_root):
    ed = editor.RichTextEditor(tk_root)
    captured = []
    ed.set_on_cursor_style(lambda st: captured.append(st))
    ed.insert_plain("ab")
    ed._apply_delta_range("1.0", "1.1", {"bold": True})
    ed.mark_set("insert", "1.0")
    ed._on_cursor_move()
    assert captured and captured[-1].get("bold") is True
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_editor.py::test_cursor_style_callback_fires_with_current_style -v`
Expected: FAIL（`set_on_cursor_style` 不存在 / AttributeError）

- [ ] **Step 3: 实现**

在 `editor.py` 的 `set_on_dirty` 方法下方追加：

```python
    def set_on_cursor_style(self, callback):
        self._on_cursor_style = callback
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_editor.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add editor.py tests/test_editor.py
git commit -m "feat: editor emits cursor-style callback for toolbar refresh"
```

---

## Task 3: 工具栏字号框随光标刷新（toolbar.py）

editor 光标移动 → toolbar `_refresh_size` 把 `size_var` 刷成当前位置字号；字号框自身获焦时跳过。

**Files:**
- Modify: `toolbar.py`（`import util`、`set_editor`、新增 `_refresh_size`）
- Test: `tests/test_editor.py`（集成测试，需显示）

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_editor.py` 末尾（需 `import util` 已在该文件可用——若没有则在文件顶部加 `import util`；当前该文件无此 import，故加上）：

先在 `tests/test_editor.py` 顶部 `import editor` 下方加一行：

```python
import util
```

再追加测试：

```python
def test_toolbar_size_box_refreshes_on_cursor_move(tk_root):
    import toolbar
    ed = editor.RichTextEditor(tk_root)
    tb = toolbar.FormatToolbar(tk_root)
    tb.set_editor(ed)
    ed.insert_plain("hello")
    ed._apply_delta_range("1.0", "1.2", {"size": 20})  # "he" = 20pt
    ed.mark_set("insert", "1.1")
    ed._on_cursor_move()
    assert tb.size_var.get() == "20"
    ed.mark_set("insert", "1.4")                        # 默认字号区
    ed._on_cursor_move()
    assert tb.size_var.get() == str(util.DEFAULT_SIZE)
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_editor.py::test_toolbar_size_box_refreshes_on_cursor_move -v`
Expected: FAIL（`_refresh_size` 未注册，size_var 保持初始值 "12"，在 20pt 区也是 "12"）

- [ ] **Step 3: 实现**

`toolbar.py` 顶部 imports 区，在 `from tkinter import colorchooser, ttk` 下方加：

```python
import util
```

把 `set_editor` 整体替换为：

```python
    def set_editor(self, editor):
        self.editor = editor
        editor.set_on_cursor_style(self._refresh_size)
```

在 `set_editor` 方法下方追加：

```python
    def _refresh_size(self, style):
        # 字号框正在被用户编辑时不覆盖，避免打架
        if self.focus_get() is self.size_box:
            return
        size = style.get("size", util.DEFAULT_SIZE)
        self.size_var.set(str(size))
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_editor.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add toolbar.py tests/test_editor.py
git commit -m "feat: toolbar size box tracks cursor position"
```

---

## Task 4: editor.delete_image（editor.py）

按 img_id 从文本流和 `_images` 移除图片。

**Files:**
- Modify: `editor.py`（新增 `delete_image`，置于 `image_source` 方法之后）
- Test: `tests/test_editor.py`

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_editor.py` 末尾：

```python
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
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_editor.py::test_delete_image_removes_from_text_and_registry -v`
Expected: FAIL（`delete_image` 不存在 / AttributeError）

- [ ] **Step 3: 实现**

在 `editor.py` 的 `image_source` 方法（以 `return meta["source"] if meta else None` 结尾）之后、`# ---- 事件 ----` 注释之前，插入：

```python
    def delete_image(self, img_id):
        idx = self._index_of_image(img_id)
        if idx is None:
            return
        self.delete(idx)
        self._images.pop(img_id, None)
        self._mark_dirty()
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_editor.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add editor.py tests/test_editor.py
git commit -m "feat: delete_image removes inline image by id"
```

---

## Task 5: 缩放浮层 Del 删除（image_resizer.py）

在浮层 canvas 绑定 `<Delete>`/`<Backspace>`，调用 `editor.delete_image` + `end_resize`。

**Files:**
- Modify: `image_resizer.py`（`__init__` 绑定区、新增 `_delete`）

- [ ] **Step 1: 实现**

`image_resizer.py` 的 `__init__` 中，在 `self.canvas.bind("<Escape>", lambda e: self._cancel())` 这一行下方追加两行：

```python
        self.canvas.bind("<Delete>", lambda e: self._delete())
        self.canvas.bind("<Backspace>", lambda e: self._delete())
```

在 `_cancel` 方法（以 `self.editor.end_resize()` 结尾）之后、`def destroy(self):` 之前，插入：

```python
    def _delete(self):
        self.editor.delete_image(self.img_id)
        self.editor.end_resize()
```

- [ ] **Step 2: 全量回归**

Run: `uv run pytest`
Expected: 全绿（无新增测试；skipped 计数与之前一致）

- [ ] **Step 3: 手动验收**

启动 `uv run python main.py`，粘贴一张图片 → 双击进入缩放浮层 → 按 Del：图片消失、浮层关闭。再保存重开：该图片不残留。

- [ ] **Step 4: 提交**

```bash
git add image_resizer.py
git commit -m "feat: delete image with Del key from resize overlay"
```

---

## Task 6: 加 pystray / keyboard 依赖

**Files:**
- Modify: `pyproject.toml`、`uv.lock`（由 `uv sync` 自动更新）

- [ ] **Step 1: 编辑 pyproject.toml**

把 `dependencies` 数组整体替换为：

```toml
dependencies = [
    "pillow>=12.3.0",
    "pystray>=5.0",
    "keyboard>=0.13",
]
```

- [ ] **Step 2: 同步锁文件**

Run: `uv sync`
Expected: 解析并安装 pystray、keyboard，更新 `uv.lock`。

- [ ] **Step 3: 验证可导入**

Run: `uv run python -c "import pystray, keyboard; print('ok')"`
Expected: 输出 `ok`

- [ ] **Step 4: 提交**

```bash
git add pyproject.toml uv.lock
git commit -m "feat: add pystray and keyboard dependencies for tray+hotkey"
```

---

## Task 7: 新建 tray.py（图标 + 状态机 + 线程派发）

纯逻辑可测：图标用 Pillow 生成；状态机 hide/show/toggle；外部线程回调经 `root.after` 派发。`start()` 不在测试中调用。

**Files:**
- Create: `tray.py`
- Test: `tests/test_tray.py`

- [ ] **Step 1: 写失败测试**

新建 `tests/test_tray.py`：

```python
import tray


class _FakeRoot:
    def __init__(self):
        self.withdrawed = False
        self.shown = False
        self.after_calls = 0

    def after(self, ms, fn):
        self.after_calls += 1
        fn()

    def withdraw(self):
        self.withdrawed = True

    def deiconify(self):
        self.shown = True

    def lift(self):
        pass

    def focus_force(self):
        pass


def test_make_icon_image():
    img = tray.make_icon_image()
    assert img.size == (64, 64)
    assert img.mode == "RGBA"


def test_tray_state_machine():
    root = _FakeRoot()
    quits = []
    hides = []
    tc = tray.TrayController(
        root,
        on_quit=lambda: quits.append(1),
        on_hide=lambda: hides.append(1),
    )
    assert tc._hidden is False
    tc.hide()
    assert tc._hidden is True
    assert root.withdrawed is True
    assert hides == [1]
    tc.toggle_visibility()      # 已隐藏 -> show
    assert tc._hidden is False
    assert root.shown is True
    tc.toggle_visibility()      # 已显示 -> hide
    assert tc._hidden is True


def test_tray_on_hotkey_marshals_via_after():
    root = _FakeRoot()
    tc = tray.TrayController(root, on_quit=lambda: None, on_hide=lambda: None)
    tc._on_hotkey()
    assert root.after_calls == 1
    # after 同步执行了 toggle -> hide
    assert tc._hidden is True
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_tray.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'tray'`）

- [ ] **Step 3: 实现**

新建 `tray.py`：

```python
"""TrayController：系统托盘 + 全局热键 Ctrl+Alt+N。

pystray 菜单与 keyboard 热键回调跑在各自线程；Tkinter 非线程安全，
所有外部线程回调一律经 root.after(0, fn) 派发回主线程。
"""

from PIL import Image, ImageDraw, ImageFont


def make_icon_image():
    """生成 64x64 圆角蓝底白色 N 的托盘图标（不引入二进制资源）。"""
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([2, 2, 62, 62], radius=12, fill=(26, 115, 232, 255))
    try:
        font = ImageFont.load_default(size=40)
    except TypeError:                # 旧版 Pillow 不支持 size 参数
        font = ImageFont.load_default()
    d.text((32, 32), "N", fill="white", font=font, anchor="mm")
    return img


class TrayController:
    def __init__(self, root, on_quit, on_hide):
        self._root = root
        self._on_quit = on_quit
        self._on_hide = on_hide
        self._hidden = False
        self._icon = None
        self._hotkey_unreg = None

    def start(self):
        try:
            self._start_impl()
        except Exception as exc:     # 托盘不可用不应阻断应用
            print("warning: tray unavailable: %s" % exc)

    def _start_impl(self):
        import pystray
        from pystray import MenuItem

        try:
            import keyboard
            self._hotkey_unreg = keyboard.add_hotkey("ctrl+alt+n", self._on_hotkey)
        except Exception:
            self._hotkey_unreg = None

        menu = pystray.Menu(
            MenuItem("显示/隐藏", self._on_menu_toggle),
            MenuItem("退出", self._on_menu_quit),
        )
        self._icon = pystray.Icon("simple-note", make_icon_image(), "Simple Note", menu)
        self._icon.run_detached()

    def stop(self):
        if self._hotkey_unreg is not None:
            try:
                import keyboard
                keyboard.remove_hotkey(self._hotkey_unreg)
            except Exception:
                pass
            self._hotkey_unreg = None
        if self._icon is not None:
            try:
                self._icon.stop()
            except Exception:
                pass
            self._icon = None

    # ---- 外部线程入口（仅派发，不碰 Tk）----
    def _on_hotkey(self):
        self._root.after(0, self.toggle_visibility)

    def _on_menu_toggle(self, _icon=None, _item=None):
        self._root.after(0, self.toggle_visibility)

    def _on_menu_quit(self, _icon=None, _item=None):
        self._root.after(0, self._on_quit)

    # ---- 主线程状态机 ----
    def toggle_visibility(self):
        if self._hidden:
            self.show()
        else:
            self.hide()

    def hide(self):
        self._hidden = True
        if self._on_hide:
            self._on_hide()
        self._root.withdraw()

    def show(self):
        self._hidden = False
        self._root.deiconify()
        self._root.lift()
        self._root.focus_force()
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_tray.py -v`
Expected: 3 PASS（这些用例不依赖显示，不会 skip）

- [ ] **Step 5: 提交**

```bash
git add tray.py tests/test_tray.py
git commit -m "feat: add TrayController with icon, state machine, and thread marshalling"
```

---

## Task 8: 接线 TrayController 到 NoteApp（app.py）

启动托盘与热键；窗口 X 最小化到托盘；退出时先停托盘。

**Files:**
- Modify: `app.py`（import、`__init__` 末尾、`WM_DELETE_WINDOW`、菜单"退出"、`on_exit`→`_real_quit`）

- [ ] **Step 1: 实现**

`app.py` 顶部，在 `from editor import RichTextEditor` 下方加一行：

```python
from tray import TrayController
```

`NoteApp.__init__` 末尾（`self.new_doc()` 这一行之后）追加：

```python
        self.tray = TrayController(
            self.root,
            on_quit=self._real_quit,
            on_hide=lambda: self.active is not None and self.active.editor.end_resize(),
        )
        self.tray.start()
```

把 `self.root.protocol("WM_DELETE_WINDOW", self.on_exit)` 整体替换为：

```python
        self.root.protocol("WM_DELETE_WINDOW", self.tray.hide)
```

把 `file_menu.add_command(label="退出", command=self.on_exit)` 整体替换为：

```python
        file_menu.add_command(label="退出", command=self._real_quit)
```

把 `def on_exit(self):` 方法整体替换为（仅重命名 + 加 `tray.stop()`）：

```python
    def _real_quit(self):
        for doc in list(self.docs):
            if doc.dirty:
                self.switch_to(doc)
                if not self._confirm_save(doc):
                    return
        self.tray.stop()
        self.root.destroy()
```

- [ ] **Step 2: 全量回归**

Run: `uv run pytest`
Expected: 全绿（无现有测试构造 NoteApp，托盘不在测试中启动）

- [ ] **Step 3: 手动验收**

启动 `uv run python main.py`，逐项验证：
- 按 Ctrl+Alt+N：窗口隐藏；再按：恢复。
- 点窗口 X：隐藏到托盘（不退出）。
- 左键托盘图标：切换显示/隐藏。
- 右键托盘图标：菜单含"显示/隐藏"与"退出"。
- 点"退出"：若有脏文档会询问，确认后托盘消失、进程结束。
- 隐藏窗口时若图片缩放浮层是打开的：浮层一并关闭。

- [ ] **Step 4: 提交**

```bash
git add app.py
git commit -m "feat: wire TrayController, minimize-to-tray on close, real quit path"
```

---

## Self-Review 结果

- **Spec 覆盖**：spec §2 → Task 1–3；§3 → Task 4–5；§4 → Task 6–8；§5 改动面 → 文件结构；§6 验收 → Task 5/8 手动验收步骤。无遗漏。
- **占位符扫描**：无 TBD/TODO；每个代码步骤含完整代码。
- **类型一致性**：`TrayController.__init__(root, on_quit, on_hide)` 在 Task 7 定义、Task 8 调用签名一致；`set_on_cursor_style` / `_on_cursor_style` / `_pending` 在 Task 1 引入、Task 2/3 复用名一致；`delete_image(img_id)` Task 4 定义、Task 5 调用一致。
- **与 spec 的偏差**：TrayController 增加了 `on_hide` 回调参数（spec §4.3 未显式列出），用于在隐藏时关闭可能打开的缩放浮层——这是 spec §4.4 "调 active editor.end_resize" 落地的必要接线，已在 Task 7/8 注明。
