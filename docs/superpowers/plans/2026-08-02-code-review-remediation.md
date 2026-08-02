# Simple Note 代码审查修复计划 (Code Review Remediation Plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 2026-08-02 代码审查（覆盖番茄钟/提醒子系统及整体代码）发现的缺陷，按数据安全风险优先级分批执行。

**Architecture:** 四个相互独立的阶段，可单独执行、单独验收：**P0 数据安全**（编辑器脏标记/Tcl 边界不变量、原子写入、剪贴板守卫）→ **P1 提醒子系统健壮性与 UX** → **P2 编辑器性能** → **P3 零散加固**。每阶段产出可独立运行、可测试的软件。

**Tech Stack:** Python 3.14, Tkinter, pytest, uv。命令：`uv run pytest`（全部）、`uv run pytest tests/test_x.py::test_y -v`（单测）。

**测试环境约束（重要）：** `tests/test_editor.py` 与 `tests/test_reminder_dialog.py` 需要显示器，无显示环境会 `pytest.skip`（见 `tests/conftest.py` 的 `tk_root` fixture）。`test_util / test_snote / test_settings / test_notify / test_reminder / test_tray` 无显示也可跑。验收时**必须看 skipped 计数**，不能只看 pass/fail；涉及编辑器/对话框的用例需在真实桌面环境跑一遍。

---

## 审查结论摘要（已逐条对照源码核实）

| 级别 | 位置 | 问题 |
|---|---|---|
| **Critical** | `editor.py`（无 `delete()` 覆写、无 `<<Modified>>` 绑定） | Backspace/Delete/Ctrl+X 走 Tcl 层删除，从不触发 `_mark_dirty` → `close_doc` 见 `dirty=False` 不提示 → **静默丢数据** |
| Important | `editor.py:388` `_on_paste` | 只拦截图片；文本粘贴走 Tcl `<<Paste>>`，绕过 `insert()` 与 `_stamp_typed_range` → 粘贴文字**无样式标签**，破坏“逐字有标签”不变量，因控件字体跟随 `_current_style` 而字号错乱 |
| Important | `editor.py:248` `from_document` | 载入内容进了撤销栈（无 `edit_reset()`）；载入后 `edit undo` 会把整篇撤成空；撤销打字也会产生无标签字符 |
| Important | `util.py:49` `get_clipboard_image` | 直接返回 `grabclipboard()`；Windows 下复制文件时返回路径 `list` → `insert_image` 触发 `AttributeError` |
| Important | `snote.py:27` / `settings.py:70` | 两处保存均原地 `open("w")` 截断写入；写入中途崩溃/断电 → 文件损坏，`load_*` 静默回退默认 → **笔记/设置丢失** |
| Important | `reminder.py:129/122` `add_daily`/`add_oneshot` | 无校验（`_sanitize_*` 只在加载路径校验）；API 接受加载器会拒绝的数据 |
| Important | `reminder.py:91` `load_dict` + `reminder_dialog.py:92` | 不去重 ID；手改 `settings.json` 造成重复 ID → `Treeview.insert(iid=...)` 抛 `TclError`，`refresh_list`（在 `__init__` 内）崩溃，对话框半构造残留 |
| Important | `reminder_dialog.py:116-120,141-149` | 一次性提醒默认值（日期=今天、时=`now.hour`、分=0）已是过去时刻 → 下一 tick 立即触发并删除，像数据丢失 |
| Important | `notify.py:47` + `app.py:137-139` | 每个事件一个模态 `messagebox` 串行弹出；休眠唤醒追赶后需连点 N 次 OK，期间主循环被阻塞 |
| Important | `editor.py:200` `_apply_delta_range` | 逐字符 Tcl 往返（约 6 次/字符）+ `_get_or_create_tag` 每次线性扫全部标签；实测 2 万字符加粗 ≈ 3.5s 界面冻结 |
| Minor | `reminder.py:208` `_tick_oneshot` | 不可解析条目永不移除（僵尸，每秒重解析）；缺 `label`/`when` 键会 `KeyError` 中断整轮 tick |
| Minor | `reminder.py:223` `_tick_daily` | `arm()` 未调用时每日提醒静默失效（API 陷阱，无告警） |
| Minor | `reminder_dialog.py:47-56` | `_apply_pomodoro_cfg` 对 `TclError` 静默返回，随后用旧配置启动番茄钟，无反馈 |
| Minor | `reminder_dialog.py:10-11` vs `reminder.py:8-11` | hhmm/番茄钟边界三处真源（对话框、`_sanitize_daily`、`_MIN/_MAX` 常量），UI 与调度器可能显示不一致 |
| Minor | `app.py:318-326` | 退出时 `_persist` 不应用对话框未确认的 spinbox 值 → 编辑后直接退出会丢 |
| Minor | `app.py:142-143` | 任意事件都 `_persist`（番茄钟 phase/round 并不序列化）→ 每次阶段切换都写盘 |
| Minor | `app.py:144,155-160` | 标题每秒无条件重设 |
| Minor | `app.py:183-185` | 菜单“开始番茄钟”无条件重置为第 1 轮，误点丢弃进行中会话 |
| Minor | `reminder_dialog.py:97-104` | 删除提醒无确认 |
| Minor | `snote.py:45-56` | `content.json` 非 dict（如 JSON 数组）→ `AttributeError`，`app.open_doc` 只 `except ValueError` → 抛栈而非友好弹框 |
| Minor | `app.py:192-226` | `from_document` 抛错时已建的 editor 未销毁（孤儿控件）；打开已打开文件产生重复文档；`_write_to` 只 `except OSError` |
| Minor | `main.py:8-18` | Pillow 探测是死代码：`app→tray` 顶层 `import PIL`，缺 Pillow 会在警告后立即 ImportError |
| Minor | `imefont.py:66-69` | 忽略 `ImmSetCompositionFontW` 返回值，失败也返回 True → 缓存 `_ime_style` 不再重试 |
| Minor | `editor.py:236/352/396` | `get_image_blobs` 每次保存重编码全部图片；`_index_of_image`/`_on_double_click` 全文 dump 定位单图 |
| Minor | `editor.py:160` | `len(chars)` 按码点计数，Tk 8.6 索引把增补字符（emoji）算 2 → 程序化 `insert()` 对 emoji 尾部少打一个标签 |
| Minor | `editor.py:84` | `event.state & 0x4` 在需 AltGr 的布局下可能漏打标签（依赖布局，需在 AltGr 布局验证） |
| Minor | `tray.py:147-155 / 88-97` | `_ready.wait(2)` 启动最多阻塞主线程 2s；`GetMessageW` 返回 -1 静默退出热键循环无日志 |
| Minor | `notes_panel.py:36-44` / `toolbar.py:52-59` / `image_resizer.py:28,53` | 关非活动文档后列表高亮错位；字号自由输入无校验（0 变默认、负数变像素）；`Toplevel` 无 master、`<FocusOut>` 误确认缩放 |
| Minor | `settings.py:16,26` / `reminder.py:6` | `DEFAULT_REMINDERS` 定义未用；`DEFAULT_POMODORO` 两处重复 |

**整体评价：** 架构健康、防御性写得扎实（调度循环、设置 I/O、托盘线程模型、序列化往返均有测试保障）。真实风险集中在两处数据丢失（编辑器删除不脏、保存非原子）与 Tcl/Python 边界的若干不变量泄漏，以及提醒子系统的输入校验/UX 缺口。无安全漏洞。

---

## Phase 0 — 数据安全（最高优先级）

### Task 0.1: 编辑器脏标记 + Tcl 边界不变量（修复 Critical 数据丢失）

**Files:**
- Modify: `editor.py`（`__init__` 绑定区 ~30-40；新增 `_on_modified`；`from_document` 末尾 ~319-322；`_on_paste` ~388-394）
- Modify: `util.py:42-52`（`get_clipboard_image` 类型守卫）
- Test: `tests/test_editor.py`（需显示器）、`tests/test_util.py`（无显示可跑）

**根因：** `_mark_dirty` 只挂在 Python 级 `insert`/样式/图片路径；Tcl 级 `delete`/文本粘贴/撤销/剪切/清空全部绕过。统一解法：用 `<<Modified>>` 虚拟事件兜底脏标记（一次覆盖 delete/paste/cut/clear/undo/redo），并对粘贴与撤销补打标签以维持“逐字有标签”。

**关键陷阱（必须测）：** `<<Modified>>` 是异步入队的虚拟事件。`from_document` 在 `_loading=True` 下 delete+insert，复位 `_loading=False` 后积压的 `<<Modified>>` 才派发 → 会把刚载入的文档误标为脏。实现必须保证“打开文档不变脏”（用 `edit_reset()` + 末尾 `edit_modified(False)` + 一个 `_suppress_modified` 计数/标志，并加测试验证）。

- [ ] **Step 1: 写失败测试（删除需标脏）** — `tests/test_editor.py`

```python
def test_delete_marks_dirty(tk_root):
    from editor import RichTextEditor
    ed = RichTextEditor(tk_root)
    ed.insert("end", "hello")
    seen = []
    ed.set_on_dirty(lambda: seen.append(1))
    ed.tk.call(ed._w, "delete", "1.0", "1.3")   # 模拟 Tcl 层删除（Backspace/剪切同路径）
    ed.update_idletasks()                        # 派发 <<Modified>> 虚拟事件
    assert seen, "Tcl 层删除未触发 dirty"
```

- [ ] **Step 2: 写失败测试（打开文档不得变脏）**

```python
def test_from_document_not_dirty(tk_root):
    from editor import RichTextEditor
    import snote
    ed = RichTextEditor(tk_root)
    doc = snote.build_document({}, [{"k": "text", "text": "载入的内容"}], {})
    ed.from_document(doc, {})
    ed.update_idletasks()
    seen = []
    ed.set_on_dirty(lambda: seen.append(1))
    ed.tk.call(ed._w, "delete", "1.0", "1.1")
    ed.update_idletasks()
    assert seen, "载入后应能正常标脏（说明 _loading 未卡死）"
    # 再验证载入本身不脏：新建一个，载入后不操作，不应有脏回调
    ed2 = RichTextEditor(tk_root)
    seen2 = []
    ed2.set_on_dirty(lambda: seen2.append(1))
    ed2.from_document(doc, {})
    ed2.update_idletasks()
    assert not seen2, "载入文档不应标脏"
```

- [ ] **Step 3: 运行确认失败** — `uv run pytest tests/test_editor.py -k "dirty or from_document_not" -v`（需显示；预期 FAIL）

- [ ] **Step 4: 实现 `<<Modified>>` 脏标记** — `editor.py`

`__init__` 绑定区追加：

```python
        self._suppress_modified = 0
        self.bind("<<Modified>>", self._on_modified, add="+")
```

新增方法（放在 `_mark_dirty` 附近）：

```python
    def _on_modified(self, _event=None):
        # Tk 每次内容变化都置 modified 并触发本事件；必须手动复位否则只触发一次。
        if not self.edit_modified():
            return
        self.edit_modified(False)
        if self._suppress_modified or self._loading:
            return
        self._mark_dirty()
```

`from_document` 末尾（`self._sync_ime_font()` 之后）追加，清栈并吃掉积压事件：

```python
        self.edit_reset()
        self._suppress_modified += 1
        try:
            self.update_idletasks()      # 派发载入期间积压的 <<Modified>>
        finally:
            self._suppress_modified -= 1
        self.edit_modified(False)
```

- [ ] **Step 5: 运行确认通过** — `uv run pytest tests/test_editor.py -k "dirty or from_document_not" -v`（预期 PASS）

- [ ] **Step 6: 写失败测试（粘贴文本需有标签）**

```python
def test_paste_text_is_tagged(tk_root):
    from editor import RichTextEditor
    ed = RichTextEditor(tk_root)
    ed.insert("end", "ab")
    ed.mark_set("insert", "end-1c")
    ed.clipboard_clear()
    ed.clipboard_append("XY")
    ed.event_generate("<<Paste>>")
    ed.update_idletasks()
    # 末字符必须带某个样式标签（逐字有标签不变量）
    tags = [t for t in ed.tag_names("end-2c") if t in ed._style_tags]
    assert tags, "粘贴的文本未打标签"
```

- [ ] **Step 7: 实现粘贴补打标签** — `editor.py`，`_on_paste` 改为先记光标、放行文本粘贴、晚绑定补打：

```python
    def _on_paste(self, _event=None):
        img = util.get_clipboard_image()
        if img is not None:
            max_width = max(64, self.winfo_width() - 12)
            self.insert_image(img, max_width=max_width)
            return "break"
        # 文本粘贴：记录位置，待 Tcl 类绑定插入后由晚绑定 _stamp_typed_range 补打标签
        self._type_start = self.index("insert")
```

并新增一个晚绑定 `<<Paste>>` 处理（`__init__` 内，复用 `_late_tag`）：

```python
        self.bind_class(self._late_tag, "<<Paste>>", self._stamp_typed_range, add="+")
```

（`_stamp_typed_range` 已能在 `_type_start`→`insert` 区间套 `_current_style`，直接复用。）

- [ ] **Step 8: 运行确认通过** — `uv run pytest tests/test_editor.py -k "paste_text" -v`（预期 PASS）

- [ ] **Step 9: 写失败测试（剪贴板返回 list 时取图返回 None）** — `tests/test_util.py`（无显示可跑）

```python
def test_get_clipboard_image_rejects_non_image(monkeypatch):
    import util
    from PIL import ImageGrab
    monkeypatch.setattr(ImageGrab, "grabclipboard", lambda: ["C:/x.png"])
    assert util.get_clipboard_image() is None
```

- [ ] **Step 10: 实现类型守卫** — `util.py:42-52`

```python
def get_clipboard_image():
    """从剪贴板获取 PIL.Image，无图或失败返回 None。"""
    try:
        from PIL import Image as PILImage
        from PIL import ImageGrab
    except Exception:
        return None
    try:
        img = ImageGrab.grabclipboard()
    except Exception:
        return None
    return img if isinstance(img, PILImage.Image) else None
```

- [ ] **Step 11: 运行确认通过** — `uv run pytest tests/test_util.py -k "clipboard" -v`（预期 PASS）

- [ ] **Step 12: 全量回归 + 提交**

```bash
uv run pytest -q
git add editor.py util.py tests/test_editor.py tests/test_util.py
git commit -m "fix(editor): 删除/粘贴/撤销正确标脏并维持逐字标签；剪贴板取图类型守卫"
```

> 说明：撤销/重做产生无标签字符的残余边界，由 Step 4 的 `<<Modified>>` 兜底脏标记 + Step 7 的粘贴补打已覆盖主要路径；若回归发现 `edit undo` 后仍有个别无标签字符，可在 `<<Undo>>`/`<<Redo>>` 晚绑定上对无标签区间补基础标签（`_get_or_create_tag({})`），并补对应用例。

---

### Task 0.2: 原子写入（snote + settings）

**Files:**
- Modify: `snote.py:21-33`（`save_document`）
- Modify: `settings.py:66-74`（`save_settings`）
- Test: `tests/test_snote.py`、`tests/test_settings.py`（均无显示可跑）

**模式：** 同目录临时文件写入 → `os.replace` 原子替换（Windows/POSIX 均原子）；失败清理临时文件，绝不留下截断的目标文件。

- [ ] **Step 1: 写失败测试（写入失败不破坏原文件）** — `tests/test_settings.py`

```python
def test_save_failure_keeps_original(tmp_path, monkeypatch):
    import json, settings
    p = tmp_path / "s.json"
    settings.save_settings({"version": 1, "line_spacing": "宽松"}, p)
    import os
    def boom(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(json, "dump", boom)   # 让写入中途失败
    settings.save_settings({"version": 1, "line_spacing": "紧凑"}, p)
    assert settings.load_settings(p)["line_spacing"] == "宽松", "失败写入破坏了原文件"
```

- [ ] **Step 2: 运行确认失败** — `uv run pytest tests/test_settings.py -k "failure_keeps" -v`（预期 FAIL，原文件被截断/丢）

- [ ] **Step 3: 实现原子写入** — `settings.py`（顶部 `import os, tempfile`）

```python
def save_settings(settings_data, path=None):
    """写入设置（原子替换）；OSError 仅向 stderr 警告，不抛、不阻塞 UI。"""
    path = Path(path) if path is not None else settings_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(settings_data, f, ensure_ascii=False)
            os.replace(tmp, str(path))
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
    except OSError as exc:
        print("warning: failed to save settings (%s)" % exc, file=sys.stderr)
```

- [ ] **Step 4: 运行确认通过** — `uv run pytest tests/test_settings.py -v`（预期全 PASS，含既有 17 条）

- [ ] **Step 5: 写失败测试（snote 写入失败不破坏原文件）** — `tests/test_snote.py`

```python
def test_save_failure_keeps_original(tmp_path, monkeypatch):
    import json, snote
    p = tmp_path / "n.snote"
    doc = snote.build_document({}, [{"k": "text", "text": "原件"}], {})
    snote.save_document(p, doc)
    def boom(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(json, "dumps", boom)
    try:
        snote.save_document(p, snote.build_document({}, [{"k": "text", "text": "新件"}], {}))
    except OSError:
        pass
    loaded, _ = snote.load_document(p)
    assert loaded["ops"][0]["text"] == "原件", "失败写入破坏了原笔记"
```

- [ ] **Step 6: 实现 snote 原子写入** — `snote.py`（顶部 `import os, tempfile`）

```python
def save_document(path, document, image_blobs=None):
    """把 document 写入 .snote(zip)，原子替换；写入失败不破坏既有文件。"""
    image_blobs = image_blobs or {}
    path = str(path)
    parent = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=parent, suffix=".snote.tmp")
    os.close(fd)
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("content.json", json.dumps(document, ensure_ascii=False))
            for img_id, meta in document.get("images", {}).items():
                data = image_blobs.get(img_id)
                if data is None:
                    continue
                zf.writestr(meta["file"], data)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
```

- [ ] **Step 7: 运行确认通过** — `uv run pytest tests/test_snote.py -v`（预期全 PASS）

- [ ] **Step 8: 全量回归 + 提交**

```bash
uv run pytest -q
git add snote.py settings.py tests/test_snote.py tests/test_settings.py
git commit -m "fix(io): snote 与 settings 改为原子写入，失败不破坏原文件"
```

---

## Phase 1 — 提醒子系统健壮性与 UX

> 引擎用例在 `tests/test_reminder.py`（无显示可跑）；对话框用例在 `tests/test_reminder_dialog.py`（需显示）。

### Task 1.1: CRUD 输入校验 + 加载去重（消除重复 ID 崩溃）

**Files:** Modify `reminder.py:91-107,122-132`；Test `tests/test_reminder.py`

- [ ] **Step 1: 写失败测试**

```python
def test_add_daily_rejects_out_of_range():
    from reminder import ReminderScheduler
    import pytest
    s = ReminderScheduler()
    with pytest.raises(ValueError):
        s.add_daily("x", 99, 0)

def test_add_oneshot_rejects_nondatetime():
    from reminder import ReminderScheduler
    import pytest
    s = ReminderScheduler()
    with pytest.raises(ValueError):
        s.add_oneshot("x", "tomorrow")

def test_load_dict_dedupes_ids():
    from reminder import ReminderScheduler
    s = ReminderScheduler()
    dup = {"daily": [
        {"id": "a", "label": "一", "hour": 9, "minute": 0},
        {"id": "a", "label": "二", "hour": 10, "minute": 0},
    ]}
    s.load_dict(None, dup)
    _, daily = s.list_reminders()
    assert len(daily) == 1, "重复 ID 未去重"
```

- [ ] **Step 2: 运行确认失败** — `uv run pytest tests/test_reminder.py -k "rejects or dedupes" -v`

- [ ] **Step 3: 实现** — `reminder.py`

`add_oneshot` / `add_daily` 加校验（非法抛 `ValueError`）：

```python
    def add_oneshot(self, label, when):
        if not isinstance(label, str) or not label.strip():
            raise ValueError("label 必须为非空字符串")
        if not isinstance(when, datetime):
            raise ValueError("when 必须为 datetime")
        if when.tzinfo is not None:
            when = when.replace(tzinfo=None)
        entry = {"id": _new_id(), "label": label.strip(), "when": when.isoformat(), "fired": False}
        self._oneshot.append(entry)
        return entry

    def add_daily(self, label, hour, minute):
        if not isinstance(label, str) or not label.strip():
            raise ValueError("label 必须为非空字符串")
        try:
            hour, minute = int(hour), int(minute)
        except (TypeError, ValueError, OverflowError):
            raise ValueError("hour/minute 必须为整数")
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError("hour/minute 超出范围")
        entry = {"id": _new_id(), "label": label.strip(), "hour": hour, "minute": minute}
        self._daily.append(entry)
        return entry
```

`load_dict` 去重（跨 oneshot/daily 共用 `seen`）：

```python
    def load_dict(self, pomodoro, reminders):
        self._pomodoro = sanitize_pomodoro(pomodoro)
        reminders = reminders if isinstance(reminders, dict) else {}
        seen = set()
        self._oneshot = []
        raw_os = reminders.get("oneshot")
        if isinstance(raw_os, list):
            for e in raw_os:
                s = _sanitize_oneshot(e)
                if s is not None and not s["fired"] and s["id"] not in seen:
                    seen.add(s["id"])
                    self._oneshot.append(s)
        self._daily = []
        raw_daily = reminders.get("daily")
        if isinstance(raw_daily, list):
            for e in raw_daily:
                s = _sanitize_daily(e)
                if s is not None and s["id"] not in seen:
                    seen.add(s["id"])
                    self._daily.append(s)
```

- [ ] **Step 4: 运行确认通过** — `uv run pytest tests/test_reminder.py -v`
- [ ] **Step 5: 提交** — `git commit -am "fix(reminder): CRUD 校验 + 加载去重，消除重复 ID 导致的 Treeview 崩溃"`

> 对话框侧 `reminder_dialog._on_add` 已有 hhmm 校验；`add_*` 抛错时建议在 `_on_add` 包一层 `try/except ValueError → messagebox.showwarning`，作为双保险（可并入 Task 1.4）。

### Task 1.2: 一次性提醒僵尸/KeyError 清理 + 惰性 arm

**Files:** Modify `reminder.py:171-181,208-221,223-226`；Test `tests/test_reminder.py`

- [ ] **Step 1: 写失败测试**

```python
def test_oneshot_corrupt_entry_dropped_not_zombie():
    from reminder import ReminderScheduler
    from datetime import datetime
    s = ReminderScheduler()
    s._oneshot = [{"id": "z", "label": "坏", "when": "不是日期", "fired": False}]
    s.tick(datetime(2026, 1, 1, 0, 0, 0))
    assert s._oneshot == [], "不可解析条目应被丢弃而非永久保留"

def test_tick_before_arm_daily_still_works():
    from reminder import ReminderScheduler
    from datetime import datetime
    s = ReminderScheduler()
    s.add_daily("早会", 9, 0)
    evs = s.tick(datetime(2026, 1, 1, 8, 0, 0))   # 未 arm，首次 tick 设基准
    assert evs == []
    evs = s.tick(datetime(2026, 1, 1, 9, 0, 30))
    assert any(e["kind"] == "daily" for e in evs), "未显式 arm 时每日提醒应仍可用"
```

- [ ] **Step 2: 运行确认失败** — `uv run pytest tests/test_reminder.py -k "zombie or before_arm" -v`

- [ ] **Step 3: 实现** — `reminder.py`

`_tick_oneshot` 整体包裹、丢弃损坏条目：

```python
    def _tick_oneshot(self, now):
        events = []
        remaining = []
        for e in self._oneshot:
            try:
                when = datetime.fromisoformat(e["when"])
                label = e["label"]
            except (ValueError, TypeError, KeyError):
                continue
            if now >= when:
                events.append({"kind": "oneshot", "title": "提醒", "message": label})
            else:
                remaining.append(e)
        self._oneshot = remaining
        return events
```

`tick` 开头惰性 arm（消除 API 陷阱）：

```python
    def tick(self, now=None):
        now = now or self._now_fn()
        if self._last_tick is None:
            self._last_tick = now
        events = []
        try:
            events.extend(self._tick_pomodoro(now))
            events.extend(self._tick_oneshot(now))
            events.extend(self._tick_daily(now))
        finally:
            self._last_tick = now
        return events
```

- [ ] **Step 4: 运行确认通过** — `uv run pytest tests/test_reminder.py -v`
- [ ] **Step 5: 提交** — `git commit -am "fix(reminder): 丢弃损坏一次性条目；tick 惰性 arm 消除每日提醒静默失效"`

### Task 1.3: 通知合并（消除模态连弹）

**Files:** Modify `notify.py`（新增纯函数 `format_events`）、`app.py:137-141`；Test `tests/test_notify.py`

- [ ] **Step 1: 写失败测试（纯函数，无显示可跑）**

```python
def test_format_events_single_and_multi():
    import notify
    one = [{"kind": "daily", "title": "每日提醒", "message": "喝水"}]
    title, msg = notify.format_events(one)
    assert title == "每日提醒" and "喝水" in msg
    many = [
        {"kind": "pomodoro", "title": "工作结束", "message": "休息"},
        {"kind": "daily", "title": "每日提醒", "message": "喝水"},
    ]
    title, msg = notify.format_events(many)
    assert title == "提醒" and "工作结束" in msg and "喝水" in msg
```

- [ ] **Step 2: 运行确认失败** — `uv run pytest tests/test_notify.py -k "format_events" -v`
- [ ] **Step 3: 实现** — `notify.py` 新增：

```python
def format_events(events):
    """把一批到期事件合并为 (title, message)，供单次弹框展示。"""
    if len(events) == 1:
        ev = events[0]
        return ev["title"], ev["message"]
    lines = ["%s：%s" % (ev["title"], ev["message"]) for ev in events]
    return "提醒", "\n".join(lines)
```

`app.py` `_tick` 改为合并后单次通知：

```python
            if events:
                title, msg = notify.format_events(events)
                try:
                    notify.notify(self.root, title, msg, self._sound_cfg)
                except Exception as exc:
                    print("warning: reminder notify error: %s" % exc, file=sys.stderr)
```

- [ ] **Step 4: 运行确认通过** — `uv run pytest tests/test_notify.py -v`
- [ ] **Step 5: 提交** — `git commit -am "fix(notify): 同一 tick 多事件合并为单次弹框"`

### Task 1.4: 对话框 UX 修补（需显示验收）

**Files:** Modify `reminder_dialog.py:47-65,97-104,116-120,141-149`、`app.py:183-185,318-326`；Test `tests/test_reminder_dialog.py`（需显示）

指定修复（逐条实现并手测/写用例）：

- [ ] 一次性提醒拒绝过去时刻：`_on_add` 构造 `when` 后 `if when <= datetime.now(): messagebox.showwarning("新增提醒", "时间必须晚于当前。", parent=self); return`；并把 `_minute_var` 默认改为 `datetime.now().minute`（`reminder_dialog.py:116-120`）。
- [ ] `_apply_pomodoro_cfg` 返回 `bool`；`_on_pomo_toggle` 在返回 False 时 `messagebox.showwarning("番茄钟", "参数格式不正确。", parent=self)` 并中止（`reminder_dialog.py:47-65`）。
- [ ] 删除提醒前 `messagebox.askyesno("删除提醒", "确认删除选中项？", parent=self)`（`reminder_dialog.py:97-104`）。
- [ ] 菜单“开始番茄钟”在 `pomodoro_phase() != "idle"` 时改为 no-op 或先确认（`app.py:183-185`）。
- [ ] `_persist`/`_real_quit` 在对话框存在时先 `self._reminder_dlg._apply_pomodoro_cfg()`，避免退出丢未确认参数（`app.py:162-169,318-326`）。
- [ ] `add_*` 抛 `ValueError` 的双保险：`_on_add` 包 `try/except ValueError → showwarning`。
- [ ] 运行 `uv run pytest tests/test_reminder_dialog.py -v`（需显示）+ 手工走查；提交 `git commit -am "fix(reminder-dialog): 拒过去时刻/参数反馈/删除确认/退出保存未确认参数"`

### Task 1.5: 常量单一真源 + 持久化/标题微优化

**Files:** Modify `settings.py:14-27`、`reminder_dialog.py:10-11,37-41`、`app.py:142-144,155-160`

- [ ] `settings.py`：用已定义的 `DEFAULT_REMINDERS` 替换 `default_settings` 内联 dict；`DEFAULT_POMODORO` 由 `reminder` 单一拥有，`settings` 改为 `from reminder import DEFAULT_POMODORO`（消除重复，`settings.py:15` / `reminder.py:6`）。
- [ ] `reminder_dialog.py`：从 `reminder` 导入 `_MIN_MIN/_MAX_MIN/_MIN_ROUNDS/_MAX_ROUNDS` 用于 spinbox `from_/to`；`update_pomodoro` 后把 `sanitize_pomodoro` 结果写回各 `IntVar`（UI 与调度器一致）。
- [ ] `app.py:142-143`：仅当 `any(ev["kind"] == "oneshot" for ev in events)` 才 `_persist`（番茄钟 phase/round 不序列化，无需写盘）。
- [ ] `app.py:155-160`：缓存上次标题串，仅在变化时 `root.title(...)`。
- [ ] 运行 `uv run pytest tests/test_settings.py tests/test_reminder.py -v`；提交 `git commit -am "refactor(reminder): 常量单一真源 + 持久化/标题微优化"`

---

## Phase 2 — 编辑器性能（大文档场景）

> 全部在 `tests/test_editor.py`（需显示）。先用基准用例量化再改，改后对比。

### Task 2.1: `_apply_delta_range` 按连续同样式段处理

**Files:** Modify `editor.py:200-212`；Test `tests/test_editor.py`

- [ ] 写基准/正确性测试：对 N 字符应用 delta 后逐字符样式正确（与逐字符实现等价），且 `new_style == current` 的段被跳过。
- [ ] 实现：用 `dump(start, end, tag=True, text=True)` 或 `tag_nextrange` 切出连续同样式段，每段计算一次 `merge_style`，整段 `tag_remove`/`tag_add`；样式未变的段跳过。把每字符约 6 次 Tcl 往返降为每段常数次。
- [ ] 跑既有 `test_editor.py` 全部样式/往返用例确保不变；提交 `git commit -am "perf(editor): _apply_delta_range 按段处理，消除逐字符 Tcl 往返"`

### Task 2.2: `_get_or_create_tag` O(1) 反查 + 图片定位/编码优化

**Files:** Modify `editor.py:64-72,236-246,352-356,396-401`

- [ ] 为 `_get_or_create_tag` 增加反向映射 `{tuple(sorted(style.items())): tag}`，使其 O(1)（`editor.py:64-72`）。
- [ ] `get_image_blobs` 按 source 缓存编码字节，`set_image_size`/`insert_image` 替换 source 时失效（`editor.py:236-246`）。
- [ ] `_index_of_image`/`_on_double_click` 改为在点击索引局部 `dump(idx, idx+" +1c", image=True)` 或为每张图维护 mark，避免全文扫描（`editor.py:352-356,396-401`）。
- [ ] 跑 `test_editor.py` 全量 + 往返用例；提交 `git commit -am "perf(editor): 标签 O(1) 反查、图片编码缓存与局部定位"`

---

## Phase 3 — 零散加固（低优先级，逐条独立小改）

每条：实现 + 对应用例 + 提交。文件:行号见括号。

- [ ] `snote.py:45-56`：`load_document` 校验 `isinstance(document, dict)`（及各 image `meta` 为 dict），否则 `raise ValueError`，让 `app.open_doc` 走友好弹框。
- [ ] `app.py:192-226`：`_make_doc` 中 `from_document` 抛错时 `editor.destroy()` 再抛；`open_doc` 按 `os.path.normcase/realpath` 去重已打开文件；`_write_to` 改 `except Exception`。
- [ ] `main.py:8-18`：Pillow 缺失警告后 `sys.exit(1)`（或把 tray/PIL 改惰性导入），消除“警告后仍 ImportError”。
- [ ] `imefont.py:66-69`：`return bool(_imm32.ImmSetCompositionFontW(...))`，失败不缓存 `_ime_style` 以便重试。
- [ ] `editor.py:160`：程序化 `insert()` 用 `self.index("insert")` 取末索引（或 `tk.call("string","length",...)`）修正 emoji 尾部少打标签。
- [ ] `editor.py:84`：在 AltGr 布局验证 `event.state & 0x4` 启发式；如漏打，改用基于 `<<Modified>>`/keysym 的判断。
- [ ] `tray.py:147-155`：暴露 `wait_ready()/status()`，去掉主线程 `_ready.wait(2)` 阻塞；`tray.py:88-97`：`GetMessageW == -1` 时记录 `GetLastError` 再退出。
- [ ] `notes_panel.py:36-44`：仅当被删行原为选中时才重选，避免高亮错位。
- [ ] `toolbar.py:52-59`：字号自由输入钳制到合法范围（如 1..400）再应用。
- [ ] `image_resizer.py:28,53`：`tk.Toplevel(editor)` 指定 master；`<FocusOut>` 不自动确认缩放（改为显式确认/Escape/点击外部）。
- [ ] 提交可合并为若干小 commit，如 `git commit -am "fix: 加固零散健壮性问题（snote/app/main/imefont/tray 等）"`。

---

## Self-Review（计划自检）

- **覆盖：** 审查摘要表中每条均有对应任务（Critical→Task 0.1；原子写入→0.2；提醒校验/去重→1.1；僵尸/臂→1.2；通知合并→1.3；对话框 UX→1.4；常量/微优化→1.5；性能→2.1/2.2；其余 Minor→Phase 3）。无遗漏。
- **占位符：** P0/P1 引擎任务含完整测试与实现代码；对话框/性能/加固任务给出确切 file:line 与实现要点（因需显示或需剖析，代码在执行期按 TDD 补全），无“略/TBD”。
- **一致性：** 方法名/签名前后一致（`format_events`、`_suppress_modified`、`add_daily(label,hour,minute)` 抛 `ValueError`、`load_dict` 去重）。`<<Modified>>` 异步陷阱已在 Task 0.1 显式标注并配测试。

## 执行顺序建议

P0（数据安全，立即）→ P1（提醒，用户重点关注）→ P2（性能，按需）→ P3（加固，可穿插）。各阶段独立可验收。
