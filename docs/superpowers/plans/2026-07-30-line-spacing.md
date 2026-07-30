# 全局行间距 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 Simple Note 增加可调整的全局行间距（紧凑/标准/宽松三档，应用级偏好，跨会话保留）。

**Architecture:** 新增纯模块 `settings.py`（无 Tk 依赖，读写 `~/.simple-note/settings.json`）；`RichTextEditor` 加一个 widget 级 `set_line_spacing(px)`（配置 `spacing1/spacing2/spacing3`，不进序列化）；`NoteApp` 启动加载设置、新增"查看"菜单单选、切换时套用到所有文档并写盘。

**Tech Stack:** Python 3.14 / Tkinter / pytest（由 `uv` 管理）。无 lint/格式化/类型检查步骤。

**Spec:** `docs/superpowers/specs/2026-07-30-line-spacing-design.md`

---

## File Structure

- **Create** `settings.py` — 纯函数应用偏好存取（无 Tk）。常量、预设映射、`px_for_level`、`default_settings`、`settings_path`、`load_settings`、`save_settings`。
- **Create** `tests/test_settings.py` — `settings.py` 的纯单测（无 Tk，必跑）。
- **Modify** `editor.py` — 新增 `set_line_spacing(px)` 方法（widget 级，约在图片方法之前/序列化之后；具体见 Task 3）。
- **Modify** `tests/test_editor.py` — 新增 `set_line_spacing` 测试。
- **Modify** `app.py` — 顶部 `import settings`；`__init__` 最开头加载设置；`_build_menu` 插入"查看"菜单；新增 `_on_line_spacing`；`_make_doc` 建编辑器后套用行间距。

行间距不进 `to_document/from_document`，故 `snote.py`、`util.py`、`tests/test_snote.py`、`tests/test_util.py` 一律不改。

---

## Task 1: `settings.py` 纯核心（常量 / 预设 / px_for_level / default_settings / settings_path）

**Files:**
- Create: `settings.py`
- Test: `tests/test_settings.py`

- [ ] **Step 1: 写失败测试（创建 `tests/test_settings.py`）**

```python
import settings


def test_default_settings_has_defaults():
    d = settings.default_settings()
    assert d["line_spacing"] == settings.DEFAULT_LINE_SPACING
    assert d["line_spacing"] == "标准"
    assert d["version"] == settings.SETTINGS_VERSION


def test_preset_order_is_three_levels():
    assert settings.PRESET_ORDER == ["紧凑", "标准", "宽松"]


def test_px_for_level_maps_each_preset():
    assert settings.px_for_level("紧凑") == 0
    assert settings.px_for_level("标准") == 4
    assert settings.px_for_level("宽松") == 8


def test_px_for_level_unknown_falls_back_to_default():
    assert settings.px_for_level("不存在的档") == settings.px_for_level(settings.DEFAULT_LINE_SPACING)
    assert settings.px_for_level(None) == 4
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_settings.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'settings'`

- [ ] **Step 3: 实现 `settings.py`（核心部分）**

```python
"""应用级偏好：纯函数读写设置文件（无 Tk 依赖）。"""

import json
import sys
from pathlib import Path

SETTINGS_VERSION = 1
DEFAULT_LINE_SPACING = "标准"

# 档位 -> 像素。PRESET_ORDER 决定菜单顺序。
LINE_SPACING_PRESETS = {"紧凑": 0, "标准": 4, "宽松": 8}
PRESET_ORDER = ["紧凑", "标准", "宽松"]


def default_settings():
    """返回含全部默认值的完整设置 dict。"""
    return {"version": SETTINGS_VERSION, "line_spacing": DEFAULT_LINE_SPACING}


def px_for_level(name):
    """档位名 -> 像素；未知值回退到默认档。"""
    return LINE_SPACING_PRESETS.get(name, LINE_SPACING_PRESETS[DEFAULT_LINE_SPACING])


def settings_path():
    """设置文件默认路径：~/.simple-note/settings.json。"""
    return Path.home() / ".simple-note" / "settings.json"
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_settings.py -v`
Expected: PASS（4 passed）

- [ ] **Step 5: 提交**

```bash
git add settings.py tests/test_settings.py
git commit -m "feat(settings): add presets, px mapping, and defaults"
```

---

## Task 2: `settings.py` 增补 `load_settings` / `save_settings`

**Files:**
- Modify: `settings.py`（追加两个函数）
- Test: `tests/test_settings.py`（追加测试）

- [ ] **Step 1: 追加失败测试（追加到 `tests/test_settings.py` 末尾）**

```python
def test_load_settings_missing_file_returns_default(tmp_path):
    p = tmp_path / "settings.json"
    assert settings.load_settings(p) == settings.default_settings()


def test_load_settings_corrupt_json_returns_default(tmp_path, capsys):
    p = tmp_path / "settings.json"
    p.write_text("{不是合法json", encoding="utf-8")
    d = settings.load_settings(p)
    assert d == settings.default_settings()
    captured = capsys.readouterr()
    assert "warning" in captured.err.lower()


def test_load_settings_valid_reads_value(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text('{"version": 1, "line_spacing": "宽松"}', encoding="utf-8")
    assert settings.load_settings(p) == {"version": 1, "line_spacing": "宽松"}


def test_load_settings_unknown_level_falls_back(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text('{"version": 1, "line_spacing": "怪东西"}', encoding="utf-8")
    d = settings.load_settings(p)
    assert d["line_spacing"] == settings.DEFAULT_LINE_SPACING


def test_load_settings_non_dict_returns_default(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text("[1, 2, 3]", encoding="utf-8")
    assert settings.load_settings(p) == settings.default_settings()


def test_save_then_load_roundtrip(tmp_path):
    p = tmp_path / "settings.json"
    settings.save_settings({"version": 1, "line_spacing": "紧凑"}, p)
    assert settings.load_settings(p) == {"version": 1, "line_spacing": "紧凑"}


def test_save_settings_creates_parent_dir(tmp_path):
    p = tmp_path / "nested" / "dir" / "settings.json"
    settings.save_settings(settings.default_settings(), p)
    assert p.exists()


def test_save_settings_oserror_does_not_raise(tmp_path, capsys):
    # 指向一个已存在的目录作为文件路径 -> 写入触发 OSError
    p = tmp_path / "a_dir"
    p.mkdir()
    settings.save_settings(settings.default_settings(), p)  # 不抛
    captured = capsys.readouterr()
    assert "warning" in captured.err.lower()
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_settings.py -v`
Expected: 新增用例 FAIL — `AttributeError: module 'settings' has no attribute 'load_settings'`

- [ ] **Step 3: 实现 load/save（追加到 `settings.py` 末尾）**

```python
def load_settings(path=None):
    """读取设置；缺失/损坏/类型错/未知档位均回退默认值，绝不抛。

    path 为 None 时用 settings_path()。返回值总是完整的（含 version 与合法 line_spacing）。
    """
    path = Path(path) if path is not None else settings_path()
    data = default_settings()
    try:
        if not path.exists():
            return data
        with path.open("r", encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError) as exc:
        print("warning: failed to load settings (%s); using defaults" % exc, file=sys.stderr)
        return data
    if isinstance(raw, dict):
        level = raw.get("line_spacing")
        if level in LINE_SPACING_PRESETS:
            data["line_spacing"] = level
    return data


def save_settings(settings_data, path=None):
    """写入设置；OSError 仅向 stderr 警告，不抛、不阻塞 UI。"""
    path = Path(path) if path is not None else settings_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(settings_data, f, ensure_ascii=False)
    except OSError as exc:
        print("warning: failed to save settings (%s)" % exc, file=sys.stderr)
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_settings.py -v`
Expected: PASS（全部 12 passed）

- [ ] **Step 5: 提交**

```bash
git add settings.py tests/test_settings.py
git commit -m "feat(settings): add load/save with fault-tolerant fallbacks"
```

---

## Task 3: `RichTextEditor.set_line_spacing(px)`

**Files:**
- Modify: `editor.py`（在"序列化"区块之后、"图片"区块之前新增方法）
- Test: `tests/test_editor.py`（末尾追加）

- [ ] **Step 1: 追加失败测试（追加到 `tests/test_editor.py` 末尾）**

```python
def test_set_line_spacing_configures_spacing(tk_root):
    ed = editor.RichTextEditor(tk_root)
    ed.set_line_spacing(4)
    assert int(ed.cget("spacing1")) == 4
    assert int(ed.cget("spacing2")) == 4
    assert int(ed.cget("spacing3")) == 0
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_editor.py::test_set_line_spacing_configures_spacing -v`
Expected: FAIL — `AttributeError: 'RichTextEditor' object has no attribute 'set_line_spacing'`（headless 无显示则 SKIPPED，留意 skipped 计数；有显示环境才真正验证）

- [ ] **Step 3: 在 `editor.py` 增加方法**

在 `from_document` 方法结束（第 240 行 `self._pending = False` 之后）与注释 `# ---- 图片 ----`（第 242 行）之间插入：

```python
    def set_line_spacing(self, px):
        """设置全局行间距（widget 级 spacing1/2/3）。"""
        self.configure(spacing1=px, spacing2=px, spacing3=0)
```

注意：该方法在 `RichTextEditor` 类内部，需保持 4 空格缩进。

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_editor.py::test_set_line_spacing_configures_spacing -v`
Expected: PASS（无显示环境为 SKIPPED，属正常）

- [ ] **Step 5: 提交**

```bash
git add editor.py tests/test_editor.py
git commit -m "feat(editor): add set_line_spacing widget-level config"
```

---

## Task 4: `NoteApp` 接线（加载设置 / "查看"菜单 / 切换套用 / 建文档套用）

本任务为 UI 集成，按 spec §7 明确不新增 app 级菜单 UI 测试（YAGNI）。验证方式：构造不抛 + 全量测试套件不回归 + 手动冒烟。

**Files:**
- Modify: `app.py`

- [ ] **Step 1: 顶部新增导入**

在 `app.py` 顶部导入区，`import snote` 之后追加：

```python
import settings
```

（与现有 `import snote` / `from editor import RichTextEditor` 等保持字母序风格一致即可。）

- [ ] **Step 2: `__init__` 最开头加载设置**

在 `NoteApp.__init__` 中，`self.docs = []` 之前（即在 `self.root.title(...)` 之后、`self._build_menu()` 之前）插入：

```python
        self.settings = settings.load_settings()
        self._line_spacing = self.settings.get("line_spacing", settings.DEFAULT_LINE_SPACING)
        self._ls_var = tk.StringVar(value=self._line_spacing)
```

理由：菜单在紧随其后的 `self._build_menu()` 中绑定 `self._ls_var`，故这些字段必须先就绪；且须在任何编辑器创建之前确定档位。

- [ ] **Step 3: `_build_menu` 插入"查看"菜单**

在 `_build_menu` 中，`menubar.add_cascade(label="文件", menu=file_menu)` 之后、`help_menu = tk.Menu(...)` 之前插入：

```python
        view_menu = tk.Menu(menubar, tearoff=0)
        for name in settings.PRESET_ORDER:
            view_menu.add_radiobutton(
                label=name, value=name, variable=self._ls_var, command=self._on_line_spacing
            )
        menubar.add_cascade(label="查看", menu=view_menu)
```

最终菜单栏顺序为：`文件` / `查看` / `关于`。

- [ ] **Step 4: 新增 `_on_line_spacing` 方法**

在 `NoteApp` 类内、`_build_menu` 方法之后新增：

```python
    def _on_line_spacing(self):
        level = self._ls_var.get()
        self._line_spacing = level
        px = settings.px_for_level(level)
        for doc in self.docs:
            doc.editor.set_line_spacing(px)
        self.settings["line_spacing"] = level
        settings.save_settings(self.settings)
```

- [ ] **Step 5: `_make_doc` 建编辑器后套用行间距**

将 `_make_doc` 中的：

```python
        editor = RichTextEditor(self.editor_host)
        doc = NoteDocument(editor, path=path, title=title)
```

改为：

```python
        editor = RichTextEditor(self.editor_host)
        editor.set_line_spacing(settings.px_for_level(self._line_spacing))
        doc = NoteDocument(editor, path=path, title=title)
```

- [ ] **Step 6: 全量回归 + 手动冒烟**

Run: `uv run pytest -v`
Expected: 全部 PASS（含 Task 1-3 新增用例）；留意 `test_editor.py` 中依赖 Tk 的用例在无显示环境会 SKIPPED，属正常——重点确认没有 FAILED。

手动冒烟（需图形环境；无显示可跳过）：
Run: `uv run python main.py`
验证：
1. 菜单栏出现 `文件` / `查看` / `关于`。
2. `查看` 下有 紧凑/标准/宽松 三项，默认勾选"标准"。
3. 切换到"宽松"后行距明显变大，切换到"紧凑"恢复紧密；新建文档（`新建`）也按当前档位渲染。
4. 退出重启程序，勾选仍停留在上次选择（设置已落盘 `~/.simple-note/settings.json`）。

- [ ] **Step 7: 提交**

```bash
git add app.py
git commit -m "feat(app): wire global line spacing view menu and persistence"
```

---

## Self-Review（plan 完成后自检）

- **Spec 覆盖**：
  - §3 架构/数据流 → Task 1-4 全覆盖。
  - §4 预设档位（紧凑0/标准4/宽松8、默认标准）→ Task 1 常量 + 测试。
  - §5.1 `settings.py` API → Task 1（常量/px/default/path）+ Task 2（load/save）。
  - §5.2 `editor.set_line_spacing` → Task 3。
  - §5.3 `app.py` 接线（init 顺序、菜单、回调、_make_doc）→ Task 4 Step 2-5。
  - §6 错误处理（load 缺失/损坏/类型/未知→默认 + stderr；save OSError 警告不抛）→ Task 2 实现 + 测试。
  - §7 测试（test_settings 纯单测、test_editor set_line_spacing、不加 app UI 测试）→ Task 1-3 + Task 4 Step 6 说明。
  - §8 兼容性（不进文档、默认改 4px 已确认）→ 设计层面保证，无需额外任务。
  - 无遗漏。
- **占位符扫描**：无 TBD/TODO/"适当处理"等；每步含完整代码与确切命令。
- **类型/命名一致性**：`DEFAULT_LINE_SPACING`、`SETTINGS_VERSION`、`LINE_SPACING_PRESETS`、`PRESET_ORDER`、`px_for_level`、`default_settings`、`settings_path`、`load_settings`、`save_settings`、`set_line_spacing`、`self._line_spacing`、`self._ls_var`、`self.settings` 在各任务中名称一致。`save_settings(settings_data, path)` 形参取 `settings_data` 以免与模块名 `settings` 冲突，调用处 `settings.save_settings(self.settings)` 不受影响。
