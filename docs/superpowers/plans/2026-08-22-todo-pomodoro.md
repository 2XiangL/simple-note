# 待办清单与番茄钟联动 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 全局待办清单：左侧双页签（笔记/待办），todo 可设为「当前任务」绑定番茄钟——每完成一轮工作阶段计数 +1，通知文案带任务名。

**Architecture:** 新建 Tk-free 纯逻辑模块 `todo.py`（`TodoStore`：CRUD/清洗/两段排序/current 绑定，模式对齐 `reminder.ReminderScheduler`）+ UI 模块 `todo_panel.py`（视图+回调，数据在 app 侧）+ `reminder.py` 小改（`task` 文案与 `work_completed` 计数信号），`app.py` 接线（Notebook 双页签、tick 回写计数、current 联动）。持久化走 `settings.json` 新增 `todos` 键。

**Tech Stack:** Python 3.14 + Tkinter/ttk（无新依赖）、pytest。

**Spec:** `docs/superpowers/specs/2026-08-22-todo-pomodoro-design.md`

**通用约定（每个任务都适用）：**

- 测试命令一律 `uv run pytest <路径> -v`（仓库用 uv 管理，pythonpath=["."]，根目录模块直接 import）
- UI 字符串/docstring/注释用**简体中文**；新 UI 文案的 en 译文在**同一任务**内补进 `lang.EN_TRANSLATIONS`（`tests/test_lang.py::test_en_dict_covers_all_t_callsites` 扫描根目录 `*.py` 的 `t("...")` 调用点强制无漏译）
- conftest autouse fixture 强制测试以 zh 运行；断言英文译文须在测试内显式 `lang.set_language("en")` 并 finally 恢复 zh
- 提交信息风格：`feat(todo):` / `feat(app):` 等中文描述（Conventional Commits + scope）
- 无 lint/typecheck；不要发明 lint 步骤
- 已知环境问题：`tests/test_editor.py::test_apply_delta_range_emoji_uses_tk_indices` 在本机预存失败（与本功能无关，HEAD 同样失败），回归时忽略该条

---

### Task 1: `todo.py` — TodoStore 纯逻辑

**Files:**
- Create: `todo.py`
- Test: `tests/test_todo.py`

**Interfaces:**
- Consumes: 无（Tk-free，零依赖）
- Produces: `todo.TodoStore`，方法 `load_dict(data)` / `to_dict()` / `list_items()` / `add(text)` / `remove(tid)` / `toggle(tid)` / `move(tid, delta)` / `set_current(tid)` / `clear_current()` / `current_id()` / `add_pomo(n)`；条目形如 `{"id": str, "text": str, "done": bool, "pomo": int}`；`MAX_POMO = 9999`。Task 5 的 app 依赖这些签名。

- [ ] **Step 1: 写失败测试**

创建 `tests/test_todo.py`：

```python
import pytest

import todo


def _texts(s):
    return [e["text"] for e in s.list_items()]


def test_load_dict_sanitizes_and_dedups():
    s = todo.TodoStore()
    s.load_dict({
        "items": [
            "junk",
            {"id": "a", "text": "  写周报 ", "done": "yes", "pomo": 3},
            {"id": "a", "text": "重复id"},                       # 同 id 丢弃，保留先出现者
            {"text": ""},                                        # 空文本丢弃
            {"id": "b", "text": "学习", "pomo": 99999},          # clamp 到 9999
            {"id": "c", "text": "坏pomo", "pomo": "x"},          # 坏 pomo 归 0
            {"id": "", "text": "缺id补发"},                      # 缺 id 补发
        ],
        "current": "zzz",  # 悬空 current -> None
    })
    items = s.list_items()
    by_id = {e["id"]: e for e in items}
    assert len(items) == 4
    assert [e["text"] for e in items] == ["学习", "坏pomo", "缺id补发", "写周报"]  # 重排为两段（未完成在前）
    assert by_id["a"]["text"] == "写周报"
    assert by_id["a"]["done"] is True
    assert by_id["a"]["pomo"] == 3
    assert by_id["b"]["pomo"] == 9999
    assert by_id["c"]["pomo"] == 0
    new_ids = [i for i in by_id if i not in ("a", "b", "c")]
    assert len(new_ids) == 1 and by_id[new_ids[0]]["text"] == "缺id补发"  # 缺 id 已补发
    assert s.current_id() is None


def test_load_dict_resegments_into_two_groups():
    # 文件被手改穿插时恢复两段不变量 [未完成…, 已完成…]
    s = todo.TodoStore()
    s.load_dict({"items": [
        {"id": "a", "text": "完成的", "done": True},
        {"id": "b", "text": "未完成", "done": False},
        {"id": "c", "text": "完成的2", "done": True},
    ]})
    assert _texts(s) == ["未完成", "完成的", "完成的2"]


def test_load_dict_bad_input_safe():
    s = todo.TodoStore()
    s.load_dict(None)
    assert s.list_items() == []
    s.load_dict({"items": "junk"})
    assert s.list_items() == []
    s.load_dict({"items": []})
    assert s.current_id() is None


def test_add_inserts_at_end_of_undone_group():
    s = todo.TodoStore()
    a = s.add("A")
    s.add("B")
    s.toggle(a["id"])      # A 完成沉底
    s.add("C")             # C 插在未完成组末尾（B 后），不在 A 前
    assert _texts(s) == ["B", "C", "A"]


def test_add_rejects_empty_or_non_string():
    s = todo.TodoStore()
    with pytest.raises(ValueError):
        s.add("")
    with pytest.raises(ValueError):
        s.add("   ")
    with pytest.raises(ValueError):
        s.add(123)
    assert s.list_items() == []  # 非法输入无残留


def test_toggle_cycles_segments_and_clears_current():
    s = todo.TodoStore()
    a = s.add("A")
    s.add("B")
    s.set_current(a["id"])
    s.toggle(a["id"])      # 完成 -> 沉底 + 解除 current
    assert s.current_id() is None
    assert _texts(s) == ["B", "A"]
    s.toggle(a["id"])      # 取消完成 -> 回未完成组末尾
    assert _texts(s) == ["A", "B"]


def test_move_within_segment_only():
    s = todo.TodoStore()
    a = s.add("A")
    b = s.add("B")
    c = s.add("C")
    s.toggle(c["id"])      # [A, B, C*]
    s.move(c["id"], -1)    # 跨段上移 -> no-op
    assert _texts(s) == ["A", "B", "C"]
    s.move(b["id"], -1)    # 段内上移
    assert _texts(s) == ["B", "A", "C"]
    s.move(a["id"], -1)    # 段首再上移 -> no-op
    assert _texts(s) == ["B", "A", "C"]
    s.move("不存在", 1)    # 未知 id -> no-op
    assert _texts(s) == ["B", "A", "C"]


def test_remove_clears_current():
    s = todo.TodoStore()
    a = s.add("A")
    s.set_current(a["id"])
    s.remove(a["id"])
    assert s.current_id() is None
    assert s.list_items() == []


def test_set_current_ignores_unknown_and_clears():
    s = todo.TodoStore()
    a = s.add("A")
    s.set_current("zzz")
    assert s.current_id() is None
    s.set_current(a["id"])
    assert s.current_id() == a["id"]
    s.clear_current()
    assert s.current_id() is None


def test_add_pomo_counts_on_current_and_clamps():
    s = todo.TodoStore()
    a = s.add("A")
    assert s.add_pomo(1) is None          # 无 current -> 丢弃
    s.set_current(a["id"])
    assert s.add_pomo(2)["pomo"] == 2
    assert s.add_pomo(0) is None          # 非正数 -> 丢弃
    assert s.add_pomo(9998)["pomo"] == 9999  # clamp


def test_to_dict_load_dict_roundtrip():
    s = todo.TodoStore()
    a = s.add("A")
    s.add("B")
    s.toggle(a["id"])
    s.set_current(s.list_items()[0]["id"])
    data = s.to_dict()
    s2 = todo.TodoStore()
    s2.load_dict(data)
    assert s2.to_dict() == data
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_todo.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'todo'`（收集阶段报错）

- [ ] **Step 3: 最小实现**

创建 `todo.py`：

```python
"""待办清单存储：Tk-free 纯逻辑（TodoStore），可无显示器单测。

两段不变量：items 恒为 [未完成…, 已完成…]，段内保持手动顺序；
完成沉底、取消完成回未完成组末尾、move 不跨段。
"""

import uuid

MAX_POMO = 9999


def _new_id():
    return uuid.uuid4().hex[:8]


def _sanitize_item(entry):
    if not isinstance(entry, dict):
        return None
    text = entry.get("text")
    if not isinstance(text, str) or not text.strip():
        return None
    try:
        pomo = int(entry.get("pomo", 0))
    except (TypeError, ValueError, OverflowError):
        pomo = 0
    rid = entry.get("id")
    if not isinstance(rid, str) or not rid:
        rid = _new_id()
    return {
        "id": rid,
        "text": text.strip(),
        "done": bool(entry.get("done")),
        "pomo": max(0, min(MAX_POMO, pomo)),
    }


class TodoStore:
    def __init__(self):
        self._items = []
        self._current = None

    # ---- 持久化 ----
    def load_dict(self, data):
        self._items = []
        self._current = None
        if not isinstance(data, dict):
            return
        seen = set()
        raw_items = data.get("items")
        if isinstance(raw_items, list):
            for e in raw_items:
                s = _sanitize_item(e)
                if s is not None and s["id"] not in seen:
                    seen.add(s["id"])
                    self._items.append(s)
        undone = [e for e in self._items if not e["done"]]
        done = [e for e in self._items if e["done"]]
        self._items = undone + done  # 手改文件穿插时恢复两段不变量
        cur = data.get("current")
        if isinstance(cur, str) and cur in seen:
            self._current = cur

    def to_dict(self):
        return {"items": [dict(e) for e in self._items], "current": self._current}

    def list_items(self):
        return [dict(e) for e in self._items]

    # ---- 内部 ----
    def _find(self, tid):
        for i, e in enumerate(self._items):
            if e["id"] == tid:
                return i
        return -1

    def _undone_end(self):
        return sum(1 for e in self._items if not e["done"])

    # ---- CRUD ----
    def add(self, text):
        if not isinstance(text, str) or not text.strip():
            raise ValueError("text 必须为非空字符串")
        entry = {"id": _new_id(), "text": text.strip(), "done": False, "pomo": 0}
        self._items.insert(self._undone_end(), entry)
        return entry

    def remove(self, tid):
        idx = self._find(tid)
        if idx < 0:
            return
        self._items.pop(idx)
        if self._current == tid:
            self._current = None

    def toggle(self, tid):
        idx = self._find(tid)
        if idx < 0:
            return
        e = self._items.pop(idx)
        e["done"] = not e["done"]
        if e["done"]:
            self._items.append(e)
            if self._current == tid:
                self._current = None
        else:
            self._items.insert(self._undone_end(), e)

    def move(self, tid, delta):
        idx = self._find(tid)
        if idx < 0 or not delta:
            return
        new_idx = idx + (1 if delta > 0 else -1)
        if new_idx < 0 or new_idx >= len(self._items):
            return
        if self._items[idx]["done"] != self._items[new_idx]["done"]:
            return  # 不跨段
        self._items[idx], self._items[new_idx] = self._items[new_idx], self._items[idx]

    # ---- 当前任务 ----
    def set_current(self, tid):
        if self._find(tid) >= 0:
            self._current = tid

    def clear_current(self):
        self._current = None

    def current_id(self):
        return self._current

    def add_pomo(self, n):
        """给当前任务累加完成番茄数；无当前任务返回 None（计数丢弃）。"""
        if not n or n <= 0:
            return None
        idx = self._find(self._current)
        if idx < 0:
            return None
        self._items[idx]["pomo"] = min(MAX_POMO, self._items[idx]["pomo"] + int(n))
        return dict(self._items[idx])
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_todo.py -v`
Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add todo.py tests/test_todo.py
git commit -m "feat(todo): TodoStore 待办清单纯逻辑（清洗/两段排序/当前任务/番茄计数）"
```

---

### Task 2: `settings.py` — todos 键

**Files:**
- Modify: `settings.py`
- Test: `tests/test_settings.py`（追加）

**Interfaces:**
- Consumes: Task 1 无关；`settings.default_settings()` / `load_settings()` 现有结构
- Produces: `settings.DEFAULT_TODOS = {"items": [], "current": None}`；`default_settings()["todos"]` 与 `load_settings()` 白名单透传。Task 5 的 app 依赖 `settings.get("todos")`。

- [ ] **Step 1: 写失败测试**

在 `tests/test_settings.py` 末尾追加：

```python
def test_default_settings_includes_todos():
    d = settings.default_settings()
    assert d["todos"] == dict(settings.DEFAULT_TODOS)
    assert d["todos"] == {"items": [], "current": None}


def test_default_settings_todos_inner_list_not_shared():
    # default_settings 每次调用须返回全新内层 list，防跨调用串改
    d1 = settings.default_settings()
    d1["todos"]["items"].append("x")
    assert settings.default_settings()["todos"] == {"items": [], "current": None}


def test_load_settings_preserves_todos(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text(
        '{"version": 1, "todos": {"items": [{"id": "a", "text": "写周报", "done": false, "pomo": 2}], "current": "a"}}',
        encoding="utf-8",
    )
    d = settings.load_settings(p)
    assert d["todos"]["items"][0]["text"] == "写周报"
    assert d["todos"]["current"] == "a"


def test_load_settings_wrong_type_todos_falls_back(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text('{"version": 1, "todos": "junk"}', encoding="utf-8")
    d = settings.load_settings(p)
    assert d["todos"] == {"items": [], "current": None}
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_settings.py -v`
Expected: 新增 4 条 FAIL（`KeyError: 'todos'` / `AttributeError: ... DEFAULT_TODOS`），原有全 PASS

- [ ] **Step 3: 最小实现**

`settings.py` 三处修改：

(1) 常量区（`DEFAULT_REMINDERS` 之后）：

```python
DEFAULT_TODOS = {"items": [], "current": None}
```

(2) `default_settings()` 增加一行（`"reminders"` 之后；`{**DEFAULT_TODOS, "items": []}` 每次生成全新内层 list）：

```python
        "todos": {**DEFAULT_TODOS, "items": []},
```

(3) `load_settings` 白名单元组改为：

```python
        for key in ("sound", "pomodoro", "reminders", "todos"):
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_settings.py -v`
Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add settings.py tests/test_settings.py
git commit -m "feat(settings): todos 键默认值与容错透传"
```

---

### Task 3: `reminder.py` — 任务名文案 + work_completed 计数

**Files:**
- Modify: `reminder.py`（`__init__` / `start_pomodoro` / `stop_pomodoro` / 新增 `set_pomodoro_task` / `_tick_pomodoro`）
- Modify: `lang.py`（`EN_TRANSLATIONS` 追加 2 条）
- Test: `tests/test_reminder.py`（追加）

**Interfaces:**
- Consumes: 无
- Produces: `start_pomodoro(now=None, task=None)`（向后兼容，旧调用不传 task 不变）；`set_pomodoro_task(task)`（idle 时忽略）；`stop_pomodoro()` 清空任务名；pomodoro 事件 dict 新增 `"work_completed": int`（本次 tick 内完成的工作阶段数，可为 0）。Task 5 的 app 依赖 `work_completed` 键与 `set_pomodoro_task`。

- [ ] **Step 1: 写失败测试**

在 `tests/test_reminder.py` 末尾追加（文件已 import `datetime`/`timedelta`/`lang`/`reminder`/`ReminderScheduler`）：

```python
def test_pomodoro_task_name_in_messages():
    t0 = datetime(2026, 8, 2, 9, 0)
    s = ReminderScheduler()
    s.update_pomodoro({"work_min": 25, "break_min": 5, "rounds": 2})
    s.start_pomodoro(t0, task="写周报")
    ev = s.tick(t0 + timedelta(minutes=25))   # 第1轮工作结束
    assert ev[0]["message"] == "第 1 轮工作结束（写周报），休息 5 分钟。"
    assert ev[0]["work_completed"] == 1
    ev = s.tick(t0 + timedelta(minutes=30))   # 休息结束 -> 第2轮工作
    assert ev[0]["work_completed"] == 0       # 休息结束不计数
    ev = s.tick(t0 + timedelta(minutes=55))   # 第2轮收官
    assert ev[0]["title"] == "番茄钟完成"
    assert ev[0]["message"] == "已完成全部 2 轮（写周报），休息一下吧。"
    assert ev[0]["work_completed"] == 1       # 最终轮收官也计 1


def test_pomodoro_without_task_keeps_plain_messages():
    t0 = datetime(2026, 8, 2, 9, 0)
    s = ReminderScheduler()
    s.update_pomodoro({"work_min": 25, "break_min": 5, "rounds": 2})
    s.start_pomodoro(t0)
    ev = s.tick(t0 + timedelta(minutes=25))
    assert ev[0]["message"] == "第 1 轮工作结束，休息 5 分钟。"
    assert ev[0]["work_completed"] == 1


def test_pomodoro_catchup_accumulates_work_completed():
    t0 = datetime(2026, 8, 2, 9, 0)
    s = ReminderScheduler()
    s.update_pomodoro({"work_min": 25, "break_min": 5, "rounds": 4})
    s.start_pomodoro(t0, task="学习")
    ev = s.tick(t0 + timedelta(minutes=200))  # 追赶跨全部阶段
    assert len(ev) == 1
    assert ev[0]["work_completed"] == 4       # 4 轮工作全部计入


def test_set_pomodoro_task_ignored_when_idle():
    t0 = datetime(2026, 8, 2, 9, 0)
    s = ReminderScheduler()
    s.update_pomodoro({"work_min": 25, "break_min": 5, "rounds": 1})
    s.set_pomodoro_task("不应生效")            # idle 忽略
    s.start_pomodoro(t0)
    ev = s.tick(t0 + timedelta(minutes=25))
    assert ev[0]["message"] == "已完成全部 1 轮，休息一下吧。"


def test_stop_pomodoro_clears_task():
    s = ReminderScheduler()
    s.start_pomodoro(datetime(2026, 8, 2, 9, 0), task="学习")
    s.stop_pomodoro()
    s.set_pomodoro_task("不应生效")            # stop 后 idle，忽略
    t1 = datetime(2026, 8, 2, 10, 0)
    s.update_pomodoro({"work_min": 25, "break_min": 5, "rounds": 1})
    s.start_pomodoro(t1)
    ev = s.tick(t1 + timedelta(minutes=25))
    assert "不应生效" not in ev[0]["message"]
    assert ev[0]["message"] == "已完成全部 1 轮，休息一下吧。"


def test_pomodoro_task_message_english():
    t0 = datetime(2026, 8, 2, 9, 0)
    lang.set_language("en")
    try:
        s = ReminderScheduler()
        s.update_pomodoro({"work_min": 25, "break_min": 5, "rounds": 1})
        s.start_pomodoro(t0, task="Report")
        ev = s.tick(t0 + timedelta(minutes=25))
        assert ev[0]["message"] == "All 1 rounds done (Report). Take a break!"
    finally:
        lang.set_language("zh")
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_reminder.py -v`
Expected: 新增 6 条 FAIL（`TypeError: start_pomodoro() got an unexpected keyword argument 'task'` 等），原有全 PASS

- [ ] **Step 3: 最小实现**

`reminder.py` 五处修改：

(1) `__init__` 增加一行（`self._phase_end = None` 之后）：

```python
        self._pomo_task = None
```

(2) `start_pomodoro` / `stop_pomodoro` 替换为：

```python
    def start_pomodoro(self, now=None, task=None):
        now = now or self._now_fn()
        self._phase = PHASE_WORK
        self._round = 1
        self._pomo_task = task
        self._phase_end = now + timedelta(minutes=self._pomodoro["work_min"])

    def stop_pomodoro(self):
        self._phase = PHASE_IDLE
        self._round = 0
        self._pomo_task = None
        self._phase_end = None
```

(3) 新增方法（`stop_pomodoro` 之后）：

```python
    def set_pomodoro_task(self, task):
        """运行中更新通知文案里的任务名；idle 时忽略。"""
        if self._phase != PHASE_IDLE:
            self._pomo_task = task
```

(4) `_tick_pomodoro` 整体替换为：

```python
    def _tick_pomodoro(self, now):
        if self._phase == PHASE_IDLE or self._phase_end is None:
            return []
        last_msg = None
        work_completed = 0
        # 追赶合并：静默推进到当前应有阶段，仅保留最后一条消息；工作完成数累计不丢
        while self._phase != PHASE_IDLE and self._phase_end is not None and now >= self._phase_end:
            if self._phase == PHASE_WORK:
                work_completed += 1
                task = self._pomo_task
                if self._round >= self._pomodoro["rounds"]:
                    if task:
                        last_msg = (
                            t("番茄钟完成"),
                            t("已完成全部 %d 轮（%s），休息一下吧。") % (self._pomodoro["rounds"], task),
                        )
                    else:
                        last_msg = (t("番茄钟完成"), t("已完成全部 %d 轮，休息一下吧。") % self._pomodoro["rounds"])
                    self._phase = PHASE_IDLE
                    self._round = 0
                    self._phase_end = None
                    break
                if task:
                    last_msg = (
                        t("工作结束"),
                        t("第 %d 轮工作结束（%s），休息 %d 分钟。") % (self._round, task, self._pomodoro["break_min"]),
                    )
                else:
                    last_msg = (
                        t("工作结束"),
                        t("第 %d 轮工作结束，休息 %d 分钟。") % (self._round, self._pomodoro["break_min"]),
                    )
                self._phase = PHASE_BREAK
                self._phase_end = self._phase_end + timedelta(minutes=self._pomodoro["break_min"])
            else:  # PHASE_BREAK
                self._round += 1
                last_msg = (t("休息结束"), t("开始第 %d 轮工作（%d 分钟）。") % (self._round, self._pomodoro["work_min"]))
                self._phase = PHASE_WORK
                self._phase_end = self._phase_end + timedelta(minutes=self._pomodoro["work_min"])
        if last_msg is None:
            return []
        return [{"kind": "pomodoro", "title": last_msg[0], "message": last_msg[1],
                 "work_completed": work_completed}]
```

(5) `lang.py` 的 `EN_TRANSLATIONS`「番茄钟 / 提醒事件」区（`"开始第 %d 轮工作（%d 分钟）。"` 之后）追加：

```python
    "第 %d 轮工作结束（%s），休息 %d 分钟。": "Round %d work finished (%s). Break for %d minutes.",
    "已完成全部 %d 轮（%s），休息一下吧。": "All %d rounds done (%s). Take a break!",
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_reminder.py tests/test_lang.py -v`
Expected: 全部 PASS（含 en 完整性扫描）

- [ ] **Step 5: 提交**

```bash
git add reminder.py lang.py tests/test_reminder.py
git commit -m "feat(reminder): 番茄钟绑定任务名文案与 work_completed 计数信号"
```

---

### Task 4: `todo_panel.py` — 待办面板 UI

**Files:**
- Create: `todo_panel.py`
- Modify: `lang.py`（`EN_TRANSLATIONS` 追加）
- Test: `tests/test_todo_panel.py`（新，需显示器——全部走 `tk_root`）

**Interfaces:**
- Consumes: 无（纯视图，不 import todo）
- Produces: `TodoPanel(master, on_add=None, on_toggle=None, on_remove=None, on_move=None, on_set_current=None, on_toggle_focus=None)`；渲染方法 `set_items(items, current_id, running)`（items 为 `list_items()` 形的 dict 列表）。Task 5 的 app 依赖此构造签名与 `set_items`。

- [ ] **Step 1: 写失败测试**

创建 `tests/test_todo_panel.py`：

```python
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
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_todo_panel.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'todo_panel'`（无显示器会整文件 skip，属预期；在开发机上运行）

- [ ] **Step 3: 最小实现**

创建 `todo_panel.py`：

```python
"""TodoPanel：待办清单面板（视图 + 回调，数据在 app 侧）。"""

import tkinter as tk
from tkinter import messagebox, ttk

from lang import t


class TodoPanel(ttk.Frame):
    def __init__(self, master=None, on_add=None, on_toggle=None, on_remove=None,
                 on_move=None, on_set_current=None, on_toggle_focus=None):
        super().__init__(master)
        self.on_add = on_add
        self.on_toggle = on_toggle
        self.on_remove = on_remove
        self.on_move = on_move
        self.on_set_current = on_set_current
        self.on_toggle_focus = on_toggle_focus
        self._running = False
        self._current_id = None
        self._ids = []  # [(tree iid, todo id)]

        top = ttk.Frame(self)
        top.pack(fill=tk.X, padx=4, pady=2)
        self._entry_var = tk.StringVar()
        ttk.Entry(top, textvariable=self._entry_var).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(top, text=t("添加"), command=self._on_add).pack(side=tk.LEFT, padx=4)

        mid = ttk.Frame(self)
        mid.pack(fill=tk.BOTH, expand=True, padx=4, pady=2)
        self._tree = ttk.Treeview(
            mid, columns=("text",), show="tree headings", selectmode="browse"
        )
        self._tree.heading("#0", text=t("状态"))
        self._tree.heading("text", text=t("内容"))
        self._tree.column("#0", width=52, stretch=False)
        self._tree.column("text", width=120)
        self._tree.pack(fill=tk.BOTH, expand=True)
        self._tree.bind("<Double-1>", self._on_double_click)
        self._tree.bind("<Button-3>", self._on_right_click)

        self._focus_btn = ttk.Button(self, text=t("开始专注"), command=self._on_focus)
        self._focus_btn.pack(fill=tk.X, padx=4, pady=2)

        self.menu = tk.Menu(self, tearoff=0)
        self.menu.add_command(label=t("设为当前任务"), command=self._menu_set_current)
        self.menu.add_command(label=t("取消当前任务"), command=self._menu_clear_current)
        self.menu.add_command(label=t("切换完成"), command=self._menu_toggle)
        self.menu.add_separator()
        self.menu.add_command(label=t("上移"), command=lambda: self._menu_move(-1))
        self.menu.add_command(label=t("下移"), command=lambda: self._menu_move(1))
        self.menu.add_separator()
        self.menu.add_command(label=t("删除"), command=self._menu_remove)

    # ---- 渲染 ----
    def set_items(self, items, current_id, running):
        sel = self._selected_id()
        for iid in self._tree.get_children():
            self._tree.delete(iid)
        self._ids = []
        for e in items:
            mark = ("▶" if e["id"] == current_id else "") + ("☑" if e["done"] else "☐")
            text = e["text"] + (t("（🍅×%d）") % e["pomo"] if e["pomo"] else "")
            iid = self._tree.insert("", tk.END, values=(text,), text=mark)
            self._ids.append((iid, e["id"]))
        self._current_id = current_id
        self._running = running
        self._focus_btn.configure(text=t("停止专注") if running else t("开始专注"))
        if sel is not None:
            self._select_id(sel)

    def _selected_id(self):
        sel = self._tree.selection()
        if not sel:
            return None
        for iid, tid in self._ids:
            if iid == sel[0]:
                return tid
        return None

    def _select_id(self, tid):
        for iid, t_ in self._ids:
            if t_ == tid:
                self._tree.selection_set(iid)
                self._tree.see(iid)
                return

    # ---- 交互 ----
    def _on_add(self):
        text = self._entry_var.get().strip()
        if not text:
            messagebox.showinfo(t("待办"), t("请输入任务内容。"), parent=self)
            return
        if self.on_add:
            self.on_add(text)
        self._entry_var.set("")

    def _on_double_click(self, _event):
        tid = self._selected_id()
        if tid and self.on_toggle:
            self.on_toggle(tid)

    def _on_focus(self):
        if self.on_toggle_focus:
            self.on_toggle_focus()

    def _on_right_click(self, event):
        iid = self._tree.identify_row(event.y)
        if not iid:
            return
        self._tree.selection_set(iid)
        self.menu.tk_popup(event.x_root, event.y_root)

    def _menu_set_current(self):
        tid = self._selected_id()
        if tid and self.on_set_current:
            self.on_set_current(tid)

    def _menu_clear_current(self):
        if self.on_set_current:
            self.on_set_current(None)

    def _menu_toggle(self):
        tid = self._selected_id()
        if tid and self.on_toggle:
            self.on_toggle(tid)

    def _menu_move(self, delta):
        tid = self._selected_id()
        if tid and self.on_move:
            self.on_move(tid, delta)

    def _menu_remove(self):
        tid = self._selected_id()
        if tid and self.on_remove:
            self.on_remove(tid)
```

`lang.py` 的 `EN_TRANSLATIONS` 末尾（`# ---- main.py ----` 区之后）追加新区：

```python
    # ---- 待办面板 ----
    "笔记": "Notes",
    "待办": "Todos",
    "状态": "Status",
    "（🍅×%d）": "(🍅×%d)",
    "开始专注": "Start Focus",
    "停止专注": "Stop Focus",
    "设为当前任务": "Set as Current Task",
    "取消当前任务": "Clear Current Task",
    "切换完成": "Toggle Done",
    "上移": "Move Up",
    "下移": "Move Down",
    "删除": "Delete",
    "请输入任务内容。": "Please enter a task description.",
```

（`"内容"`、`"添加"` 已存在，勿重复添加。）

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_todo_panel.py tests/test_lang.py -v`
Expected: 全部 PASS（含 en 完整性扫描）

- [ ] **Step 5: 提交**

```bash
git add todo_panel.py lang.py tests/test_todo_panel.py
git commit -m "feat(todo-panel): 待办面板视图（状态符/番茄计数/右键菜单/专注按钮）"
```

---

### Task 5: `app.py` — Notebook 接线与计数回写

**Files:**
- Modify: `app.py`
- Modify: `tests/test_reminder_dialog.py`（更新 1 条既有裸对象测试）
- Test: `tests/test_app.py`（追加 + import 区补充）

**Interfaces:**
- Consumes: Task 1 `TodoStore`；Task 2 `settings["todos"]`；Task 3 `start_pomodoro(task=)` / `set_pomodoro_task` / 事件 `work_completed`；Task 4 `TodoPanel(...) / set_items(items, current_id, running)`
- Produces: `NoteApp.todos`（TodoStore）、`NoteApp.todo_panel`（TodoPanel）、`NoteApp.sidebar`（ttk.Notebook，tabs = [笔记, 待办]）；`_persist` 序列化 todos。

- [ ] **Step 1: 写失败测试**

`tests/test_app.py` 顶部 import 区确保包含（已有则跳过）：

```python
from datetime import datetime, timedelta
from tkinter import ttk
import reminder
import todo
```

（`from types import SimpleNamespace`、`import app` / `from app import NoteApp` 文件已有。）

文件末尾追加：

```python
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
```

同时更新 `tests/test_reminder_dialog.py::test_app_start_pomodoro_idle_starts`（`_start_pomodoro` 现在会刷新待办面板，裸对象须补属性）：

```python
def test_app_start_pomodoro_idle_starts():
    from types import SimpleNamespace

    import todo
    from app import NoteApp

    app = NoteApp.__new__(NoteApp)
    sched = reminder.ReminderScheduler()
    app.scheduler, app.root = sched, _FakeRoot()
    app._title_cache = None
    app.todos = todo.TodoStore()
    app.todo_panel = SimpleNamespace(set_items=lambda *a, **k: None)
    app._start_pomodoro()
    assert sched.pomodoro_phase() == reminder.PHASE_WORK
```

（`test_app_start_pomodoro_noop_when_running` 提前 return 不触面板，无需改。）

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_app.py tests/test_reminder_dialog.py -v`
Expected: 新增 6 条 FAIL（`AttributeError: 'NoteApp' object has no attribute 'todos'` / `'_todo_set_current'` 等）；`test_app_start_pomodoro_idle_starts` FAIL（`AttributeError: ... 'todo_panel'`）；其余 PASS

- [ ] **Step 3: 最小实现**

`app.py` 六处修改：

(1) import 区：`import notify` 之后加一行；`from search_dialog import SearchDialog` 之后加一行：

```python
import todo
```

```python
from todo_panel import TodoPanel
```

(2) `__init__`：`self.scheduler.arm(datetime.now())` 之后加：

```python
        self.todos = todo.TodoStore()
        self.todos.load_dict(self.settings.get("todos"))
```

(3) `__init__` 的面板构造替换（原 `self.panel = NotesPanel(self.body, ...)` 与 `self.body.add(self.panel, ...)` 两段）：

```python
        self.sidebar = ttk.Notebook(self.body)
        self.panel = NotesPanel(
            self.sidebar,
            on_switch=self.switch_to,
            on_save=lambda d: self.save(d),
            on_save_as=lambda d: self.save_as(d),
            on_close=lambda d: self.close_doc(d),
        )
        self.sidebar.add(self.panel, text=t("笔记"))
        self.todo_panel = TodoPanel(
            self.sidebar,
            on_add=self._todo_add,
            on_toggle=self._todo_toggle,
            on_remove=self._todo_remove,
            on_move=self._todo_move,
            on_set_current=self._todo_set_current,
            on_toggle_focus=self._todo_toggle_focus,
        )
        self.sidebar.add(self.todo_panel, text=t("待办"))
        self.body.add(self.sidebar, minsize=150, width=180)
```

(4) `_tick`：在 `if any(ev["kind"] == "oneshot" ...)` 块之后、`self._refresh_title(now)` 之前插入：

```python
            pomo_ev = next((ev for ev in events if ev["kind"] == "pomodoro"), None)
            if pomo_ev is not None and pomo_ev.get("work_completed", 0) > 0:
                if self.todos.add_pomo(pomo_ev["work_completed"]) is not None:
                    self._persist()
                self._todo_refresh()
```

(5) `_persist`：在 `self.settings["reminders"] = reminders` 之后加一行：

```python
        self.settings["todos"] = self.todos.to_dict()
```

(6) `_stop_pomodoro` 之后新增待办区块；`_start_pomodoro` / `_stop_pomodoro` 末尾各加一行 `self._todo_refresh()`：

```python
    def _start_pomodoro(self):
        if self.scheduler.pomodoro_phase() != "idle":
            return
        self.scheduler.start_pomodoro(datetime.now())
        self._refresh_title()
        self._todo_refresh()

    def _stop_pomodoro(self):
        self.scheduler.stop_pomodoro()
        self._refresh_title()
        self._todo_refresh()

    # ---- 待办 ----
    def _todo_refresh(self):
        self.todo_panel.set_items(
            self.todos.list_items(),
            self.todos.current_id(),
            self.scheduler.pomodoro_phase() != "idle",
        )

    def _todo_changed(self):
        self._persist()
        self._todo_refresh()

    def _on_current_changed(self):
        tid = self.todos.current_id()
        label = None
        if tid is not None:
            for e in self.todos.list_items():
                if e["id"] == tid:
                    label = e["text"]
                    break
        self.scheduler.set_pomodoro_task(label)

    def _todo_add(self, text):
        self.todos.add(text)
        self._todo_changed()

    def _todo_toggle(self, tid):
        self.todos.toggle(tid)
        self._on_current_changed()
        self._todo_changed()

    def _todo_remove(self, tid):
        self.todos.remove(tid)
        self._on_current_changed()
        self._todo_changed()

    def _todo_move(self, tid, delta):
        self.todos.move(tid, delta)
        self._todo_changed()

    def _todo_set_current(self, tid):
        if tid is None:
            self.todos.clear_current()
        else:
            self.todos.set_current(tid)
        self._on_current_changed()
        self._todo_changed()

    def _todo_toggle_focus(self):
        if self.scheduler.pomodoro_phase() == "idle":
            tid = self.todos.current_id()
            if tid is None:
                messagebox.showinfo(t("待办"), t("请先在右键菜单中设为当前任务。"))
                return
            label = next(e["text"] for e in self.todos.list_items() if e["id"] == tid)
            self.scheduler.start_pomodoro(datetime.now(), task=label)
        else:
            self.scheduler.stop_pomodoro()
        self._refresh_title()
        self._todo_refresh()
```

`lang.py` 的 `EN_TRANSLATIONS`「待办面板」区追加：

```python
    "请先在右键菜单中设为当前任务。": "Right-click a task to set it as the current task first.",
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_app.py tests/test_reminder_dialog.py tests/test_lang.py -v`
Expected: 全部 PASS（`test_app` 的个别 `tk_root` 用例因已知 Tk 间歇问题偶发 skip 属正常，重跑确认）

- [ ] **Step 5: 提交**

```bash
git add app.py lang.py tests/test_app.py tests/test_reminder_dialog.py
git commit -m "feat(app): 左侧双页签接线待办清单与番茄钟计数回写"
```

---

### Task 6: AGENTS.md 更新 + 全量回归

**Files:**
- Modify: `AGENTS.md`

**Interfaces:**
- Consumes: Task 1–5 全部落地的最终形态
- Produces: 文档更新（无代码接口）

- [ ] **Step 1: 更新 AGENTS.md**

四处修改：

(1) `## Environment gotchas` 的 headless 测试清单：无显示器名单追加 `test_todo`；需显示器名单追加 `test_todo_panel`（原句里 `test_editor`, `test_notes_panel`, ... need a display 处）。

(2) `## Architecture` 增加条目（`reminder.py` 条目之后）：

```markdown
- `todo.py` — Tk-free 待办清单存储 `TodoStore`（清洗/CRUD/两段排序/current 绑定/`add_pomo` 番茄计数），模式同 `reminder.ReminderScheduler`。两段不变量：items 恒为 `[未完成…, 已完成…]`，段内手动顺序；`move` 不跨段。持久化在 `settings.json` 的 `todos` 键（`{"items": [...], "current": id|null}`）。
```

(3) `## Architecture` 增加条目（`search_dialog.py` 条目之后）：

```markdown
- `todo_panel.py` — 左侧「待办」页签 `TodoPanel(ttk.Frame)`：视图+回调模式（数据在 `app.NoteApp.todos`），`set_items(items, current_id, running)` 全量重绘。番茄钟联动：`reminder.start_pomodoro(task=...)` 绑定当前任务名，pomodoro 事件的 `work_completed` 由 `app._tick` 回写 `todos.add_pomo`；current 变化经 `_on_current_changed` 同步 `scheduler.set_pomodoro_task`。左 pane 是 `ttk.Notebook`（笔记/待办两页签），`NoteApp.panel`（NotesPanel）挂在其第一页。
```

(4) `## Conventions` 提醒数据持久化条目更新为同时提及 todos（`sound`/`pomodoro`/`reminders`/`todos` 键；深度清洗在 `todo.TodoStore.load_dict`）。

- [ ] **Step 2: 全量回归**

Run: `uv run pytest -q`
Expected: 除已知预存失败 `tests/test_editor.py::test_apply_delta_range_emoji_uses_tk_indices`（本机 Tk emoji 索引问题，与本功能无关）外全部 PASS；skip 数 ≤ 常规 Tk 间歇水平

- [ ] **Step 3: 提交**

```bash
git add AGENTS.md
git commit -m "docs(agents): 记录 todo 模块架构与测试清单更新"
```
