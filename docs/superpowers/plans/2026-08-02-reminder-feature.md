# 定时任务提醒功能 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 Simple Note 增加番茄钟倒计时 + 一次性/每日固定时间提醒，模态框+提示音通知（支持自定义 .wav），全部持久化到 settings.json。

**Architecture:** Tk-free 纯逻辑调度引擎 `reminder.py`（注入时钟、可无显示器单测）由 `app.py` 用 `root.after(1000, ...)` 每秒在主线程驱动；通知经 `notify.py`（唤回窗口+winsound+模态框）；管理 UI 为非模态 `reminder_dialog.py`。全程主线程单线程，不引入后台线程或新依赖。

**Tech Stack:** Python 3.14 / Tkinter / pytest（uv 管理）/ winsound（Windows 标准库）

**Spec:** `docs/superpowers/specs/2026-08-02-reminder-feature-design.md`

**通用命令：**
- 跑全部测试：`uv run pytest`
- 跑单个测试：`uv run pytest tests/test_x.py::test_name -v`
- 跑应用（手动验证）：`uv run python main.py`

**文件结构：**
- 改 `settings.py`：新增 `sound`/`pomodoro`/`reminders` 三个键的容错读写。
- 新 `reminder.py`：调度引擎 + 数据模型（Tk-free 纯逻辑）。
- 新 `notify.py`：`resolve_sound`（纯函数）+ `notify`（UI 胶水）。
- 新 `reminder_dialog.py`：管理对话框（UI 组件）。
- 改 `app.py`：菜单接线、`after` 循环、标题栏、持久化。
- 新测试：`tests/test_reminder.py`、`tests/test_notify.py`（无显示器）；`tests/test_reminder_dialog.py`（需显示器）；扩展 `tests/test_settings.py`。
- 改 `AGENTS.md`：架构与测试清单。

---

## Task 1: settings.py 扩展三个新键

**Files:**
- Modify: `settings.py`
- Test: `tests/test_settings.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_settings.py` 末尾追加：

```python
def test_default_settings_includes_new_keys():
    d = settings.default_settings()
    assert d["sound"] == {"mode": "system", "path": ""}
    assert d["pomodoro"] == {"work_min": 25, "break_min": 5, "rounds": 4}
    assert d["reminders"] == {"oneshot": [], "daily": []}


def test_load_settings_preserves_new_keys(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text(
        '{"version": 1, "line_spacing": "紧凑", '
        '"sound": {"mode": "custom", "path": "C:/a.wav"}, '
        '"pomodoro": {"work_min": 30, "break_min": 10, "rounds": 2}, '
        '"reminders": {"oneshot": [], "daily": [{"id": "x", "label": "hi", "hour": 8, "minute": 0}]}}',
        encoding="utf-8",
    )
    d = settings.load_settings(p)
    assert d["sound"] == {"mode": "custom", "path": "C:/a.wav"}
    assert d["pomodoro"] == {"work_min": 30, "break_min": 10, "rounds": 2}
    assert d["reminders"]["daily"][0]["label"] == "hi"


def test_load_settings_old_file_without_new_keys_gets_defaults(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text('{"version": 1, "line_spacing": "宽松"}', encoding="utf-8")
    d = settings.load_settings(p)
    assert d["line_spacing"] == "宽松"
    assert d["sound"] == {"mode": "system", "path": ""}
    assert d["pomodoro"] == {"work_min": 25, "break_min": 5, "rounds": 4}
    assert d["reminders"] == {"oneshot": [], "daily": []}


def test_load_settings_wrong_type_new_keys_falls_back(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text('{"version": 1, "sound": "junk", "pomodoro": [1], "reminders": "x"}', encoding="utf-8")
    d = settings.load_settings(p)
    assert d["sound"] == {"mode": "system", "path": ""}
    assert d["pomodoro"] == {"work_min": 25, "break_min": 5, "rounds": 4}
    assert d["reminders"] == {"oneshot": [], "daily": []}


def test_save_load_roundtrip_with_new_keys(tmp_path):
    p = tmp_path / "settings.json"
    data = settings.default_settings()
    data["pomodoro"] = {"work_min": 50, "break_min": 10, "rounds": 3}
    data["reminders"] = {"oneshot": [], "daily": [{"id": "d1", "label": "喝水", "hour": 8, "minute": 0}]}
    settings.save_settings(data, p)
    assert settings.load_settings(p) == data
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_settings.py -v`
Expected: 新增的 5 个测试 FAIL（`default_settings` 无新键 / 键被丢弃），原有测试 PASS。

- [ ] **Step 3: 实现 settings.py 扩展**

在 `settings.py` 的 `PRESET_ORDER` 之后加入默认常量：

```python
DEFAULT_SOUND = {"mode": "system", "path": ""}
DEFAULT_POMODORO = {"work_min": 25, "break_min": 5, "rounds": 4}
DEFAULT_REMINDERS = {"oneshot": [], "daily": []}
```

把 `default_settings` 改为：

```python
def default_settings():
    """返回含全部默认值的完整设置 dict。"""
    return {
        "version": SETTINGS_VERSION,
        "line_spacing": DEFAULT_LINE_SPACING,
        "sound": dict(DEFAULT_SOUND),
        "pomodoro": dict(DEFAULT_POMODORO),
        "reminders": {"oneshot": [], "daily": []},
    }
```

把 `load_settings` 中 `if isinstance(raw, dict):` 块改为：

```python
    if isinstance(raw, dict):
        level = raw.get("line_spacing")
        if level in LINE_SPACING_PRESETS:
            data["line_spacing"] = level
        for key in ("sound", "pomodoro", "reminders"):
            val = raw.get(key)
            if isinstance(val, dict):
                data[key] = val
    return data
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_settings.py -v`
Expected: 全部 PASS。

- [ ] **Step 5: 提交**

```bash
git add settings.py tests/test_settings.py
git commit -m "feat(settings): persist sound/pomodoro/reminders keys tolerantly"
```

---

## Task 2: reminder.py 数据模型 + 持久化 + CRUD

**Files:**
- Create: `reminder.py`
- Test: `tests/test_reminder.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_reminder.py`：

```python
from datetime import datetime

import reminder
from reminder import ReminderScheduler


def test_default_pomodoro_config():
    s = ReminderScheduler()
    assert s.pomodoro_config() == {"work_min": 25, "break_min": 5, "rounds": 4}


def test_add_and_list():
    s = ReminderScheduler()
    s.add_daily("喝水", 8, 0)
    s.add_oneshot("开会", datetime(2026, 8, 2, 20, 0))
    oneshot, daily = s.list_reminders()
    assert len(daily) == 1 and daily[0]["label"] == "喝水"
    assert len(oneshot) == 1 and oneshot[0]["label"] == "开会"
    assert oneshot[0]["when"] == "2026-08-02T20:00:00"


def test_remove():
    s = ReminderScheduler()
    e = s.add_daily("喝水", 8, 0)
    s.remove(e["id"])
    _, daily = s.list_reminders()
    assert daily == []


def test_to_load_roundtrip():
    s = ReminderScheduler()
    s.update_pomodoro({"work_min": 50, "break_min": 10, "rounds": 3})
    s.add_daily("喝水", 8, 0)
    s.add_oneshot("开会", datetime(2026, 8, 2, 20, 0))
    pomo, rem = s.to_dict()
    s2 = ReminderScheduler()
    s2.load_dict(pomo, rem)
    assert s2.to_dict() == (pomo, rem)


def test_sanitize_pomodoro_clamps_and_coerces():
    assert reminder.sanitize_pomodoro({"work_min": "abc", "break_min": 999, "rounds": 0}) == {
        "work_min": 25, "break_min": 180, "rounds": 1,
    }
    assert reminder.sanitize_pomodoro("junk") == {"work_min": 25, "break_min": 5, "rounds": 4}


def test_load_dict_drops_malformed_entries():
    s = ReminderScheduler()
    s.load_dict(
        {"work_min": 25, "break_min": 5, "rounds": 4},
        {
            "oneshot": [
                {"id": "a", "label": "ok", "when": "2026-08-02T20:00:00"},
                {"id": "b", "label": "bad-when", "when": "不是日期"},
                {"label": "no-id-ok", "when": "2026-08-02T21:00:00"},
                "not-a-dict",
            ],
            "daily": [
                {"id": "c", "label": "ok", "hour": 8, "minute": 0},
                {"id": "d", "label": "bad-hour", "hour": 99, "minute": 0},
                {"id": "e", "label": "no-minute"},
            ],
        },
    )
    oneshot, daily = s.list_reminders()
    assert [e["label"] for e in oneshot] == ["ok", "no-id-ok"]
    assert [e["label"] for e in daily] == ["ok"]


def test_load_dict_never_raises_on_garbage():
    s = ReminderScheduler()
    s.load_dict(None, None)
    s.load_dict([1, 2], "junk")
    assert s.list_reminders() == ([], [])
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_reminder.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'reminder'`）。

- [ ] **Step 3: 实现 reminder.py 骨架（数据模型/CRUD/持久化）**

创建 `reminder.py`：

```python
"""提醒调度引擎：番茄钟 + 一次性/每日提醒。Tk-free 纯逻辑，可无显示器单测。"""

import uuid
from datetime import datetime, timedelta

DEFAULT_POMODORO = {"work_min": 25, "break_min": 5, "rounds": 4}

_MIN_MIN = 1
_MAX_MIN = 180
_MIN_ROUNDS = 1
_MAX_ROUNDS = 12

PHASE_IDLE = "idle"
PHASE_WORK = "work"
PHASE_BREAK = "break"


def _new_id():
    return uuid.uuid4().hex[:8]


def _clamp_int(val, lo, hi, default):
    try:
        n = int(val)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


def sanitize_pomodoro(cfg):
    """清洗番茄钟配置；越界/非法按字段回退默认，绝不抛。"""
    cfg = cfg if isinstance(cfg, dict) else {}
    d = dict(DEFAULT_POMODORO)
    d["work_min"] = _clamp_int(cfg.get("work_min"), _MIN_MIN, _MAX_MIN, d["work_min"])
    d["break_min"] = _clamp_int(cfg.get("break_min"), _MIN_MIN, _MAX_MIN, d["break_min"])
    d["rounds"] = _clamp_int(cfg.get("rounds"), _MIN_ROUNDS, _MAX_ROUNDS, d["rounds"])
    return d


def _sanitize_oneshot(entry):
    if not isinstance(entry, dict):
        return None
    label = entry.get("label")
    when = entry.get("when")
    if not isinstance(label, str) or not isinstance(when, str):
        return None
    try:
        datetime.fromisoformat(when)
    except ValueError:
        return None
    rid = entry.get("id")
    if not isinstance(rid, str) or not rid:
        rid = _new_id()
    return {"id": rid, "label": label, "when": when, "fired": bool(entry.get("fired"))}


def _sanitize_daily(entry):
    if not isinstance(entry, dict):
        return None
    label = entry.get("label")
    if not isinstance(label, str):
        return None
    try:
        hour = int(entry.get("hour"))
        minute = int(entry.get("minute"))
    except (TypeError, ValueError):
        return None
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    rid = entry.get("id")
    if not isinstance(rid, str) or not rid:
        rid = _new_id()
    return {"id": rid, "label": label, "hour": hour, "minute": minute}


class ReminderScheduler:
    def __init__(self, now_fn=datetime.now):
        self._now_fn = now_fn
        self._pomodoro = dict(DEFAULT_POMODORO)
        self._oneshot = []
        self._daily = []
        self._phase = PHASE_IDLE
        self._round = 0
        self._phase_end = None
        self._last_tick = None

    # ---- 持久化 ----
    def load_dict(self, pomodoro, reminders):
        self._pomodoro = sanitize_pomodoro(pomodoro)
        reminders = reminders if isinstance(reminders, dict) else {}
        self._oneshot = []
        raw_os = reminders.get("oneshot")
        if isinstance(raw_os, list):
            for e in raw_os:
                s = _sanitize_oneshot(e)
                if s is not None and not s["fired"]:
                    self._oneshot.append(s)
        self._daily = []
        raw_daily = reminders.get("daily")
        if isinstance(raw_daily, list):
            for e in raw_daily:
                s = _sanitize_daily(e)
                if s is not None:
                    self._daily.append(s)

    def to_dict(self):
        return (
            dict(self._pomodoro),
            {"oneshot": [dict(e) for e in self._oneshot], "daily": [dict(e) for e in self._daily]},
        )

    # ---- 配置 / CRUD ----
    def pomodoro_config(self):
        return dict(self._pomodoro)

    def update_pomodoro(self, cfg):
        self._pomodoro = sanitize_pomodoro(cfg)

    def add_oneshot(self, label, when):
        entry = {"id": _new_id(), "label": label, "when": when.isoformat(), "fired": False}
        self._oneshot.append(entry)
        return entry

    def add_daily(self, label, hour, minute):
        entry = {"id": _new_id(), "label": label, "hour": hour, "minute": minute}
        self._daily.append(entry)
        return entry

    def remove(self, rid):
        self._oneshot = [e for e in self._oneshot if e["id"] != rid]
        self._daily = [e for e in self._daily if e["id"] != rid]

    def list_reminders(self):
        return [dict(e) for e in self._oneshot], [dict(e) for e in self._daily]
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_reminder.py -v`
Expected: 全部 PASS。

- [ ] **Step 5: 提交**

```bash
git add reminder.py tests/test_reminder.py
git commit -m "feat(reminder): add scheduler data model, CRUD and tolerant loading"
```

---

## Task 3: reminder.py 番茄钟状态机

**Files:**
- Modify: `reminder.py`
- Test: `tests/test_reminder.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_reminder.py` 末尾追加：

```python
from datetime import timedelta


def test_pomodoro_work_to_break_to_completion():
    t0 = datetime(2026, 8, 2, 9, 0)
    s = ReminderScheduler()
    s.update_pomodoro({"work_min": 25, "break_min": 5, "rounds": 2})
    s.start_pomodoro(t0)
    assert s.pomodoro_phase() == "work"

    ev = s.tick(t0 + timedelta(minutes=25))   # 第1轮工作结束 -> 休息
    assert len(ev) == 1 and ev[0]["kind"] == "pomodoro"
    assert s.pomodoro_phase() == "break"

    ev = s.tick(t0 + timedelta(minutes=30))   # 休息结束 -> 第2轮工作
    assert s.pomodoro_phase() == "work"

    ev = s.tick(t0 + timedelta(minutes=55))   # 第2轮工作结束 -> 完成
    assert s.pomodoro_phase() == "idle"
    assert ev[0]["title"] == "番茄钟完成"


def test_pomodoro_stop_resets_idle():
    s = ReminderScheduler()
    s.start_pomodoro(datetime(2026, 8, 2, 9, 0))
    s.stop_pomodoro()
    assert s.pomodoro_phase() == "idle"
    assert s.pomodoro_remaining() is None


def test_pomodoro_catchup_coalesces_to_one_event():
    t0 = datetime(2026, 8, 2, 9, 0)
    s = ReminderScheduler()
    s.update_pomodoro({"work_min": 25, "break_min": 5, "rounds": 4})
    s.start_pomodoro(t0)
    ev = s.tick(t0 + timedelta(minutes=200))  # 远超全部阶段
    assert len(ev) == 1                        # 合并为一条
    assert ev[0]["title"] == "番茄钟完成"
    assert s.pomodoro_phase() == "idle"


def test_pomodoro_catchup_partial_lands_correct_phase():
    t0 = datetime(2026, 8, 2, 9, 0)
    s = ReminderScheduler()
    s.update_pomodoro({"work_min": 25, "break_min": 5, "rounds": 4})
    s.start_pomodoro(t0)
    ev = s.tick(t0 + timedelta(minutes=30))   # 跨过第1轮工作(25)与休息(30)
    assert len(ev) == 1
    assert s.pomodoro_phase() == "work"
    assert s._round == 2


def test_pomodoro_remaining_format():
    t0 = datetime(2026, 8, 2, 9, 0)
    s = ReminderScheduler()
    s.update_pomodoro({"work_min": 25, "break_min": 5, "rounds": 4})
    s.start_pomodoro(t0)
    assert s.pomodoro_remaining(t0) == ("工作中", "25:00", "第1/共4轮")
    assert s.pomodoro_remaining(t0 + timedelta(minutes=10)) == ("工作中", "15:00", "第1/共4轮")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_reminder.py -v -k pomodoro`
Expected: FAIL（`ReminderScheduler` 无 `start_pomodoro`/`tick`/`pomodoro_phase` 等）。

- [ ] **Step 3: 实现番茄钟状态机**

在 `ReminderScheduler` 类中（`list_reminders` 之后）追加：

```python
    # ---- 番茄钟 ----
    def start_pomodoro(self, now=None):
        now = now or self._now_fn()
        self._phase = PHASE_WORK
        self._round = 1
        self._phase_end = now + timedelta(minutes=self._pomodoro["work_min"])

    def stop_pomodoro(self):
        self._phase = PHASE_IDLE
        self._round = 0
        self._phase_end = None

    def pomodoro_phase(self):
        return self._phase

    def pomodoro_remaining(self, now=None):
        """idle -> None；否则 (阶段中文, "MM:SS", "第N/共M轮")。"""
        if self._phase == PHASE_IDLE or self._phase_end is None:
            return None
        now = now or self._now_fn()
        total = max(0, int((self._phase_end - now).total_seconds()))
        mm, ss = divmod(total, 60)
        phase_cn = "工作中" if self._phase == PHASE_WORK else "休息中"
        return (phase_cn, "%02d:%02d" % (mm, ss), "第%d/共%d轮" % (self._round, self._pomodoro["rounds"]))

    # ---- 主循环 ----
    def tick(self, now=None):
        """推进状态，返回到期事件列表。事件形如 {"kind","title","message"}。"""
        now = now or self._now_fn()
        events = []
        try:
            events.extend(self._tick_pomodoro(now))
        finally:
            self._last_tick = now
        return events

    def _tick_pomodoro(self, now):
        if self._phase == PHASE_IDLE or self._phase_end is None:
            return []
        last_msg = None
        # 追赶合并：静默推进到当前应有阶段，仅保留最后一条消息
        while self._phase != PHASE_IDLE and self._phase_end is not None and now >= self._phase_end:
            if self._phase == PHASE_WORK:
                if self._round >= self._pomodoro["rounds"]:
                    last_msg = ("番茄钟完成", "已完成全部 %d 轮，休息一下吧。" % self._pomodoro["rounds"])
                    self._phase = PHASE_IDLE
                    self._round = 0
                    self._phase_end = None
                    break
                last_msg = ("工作结束", "第 %d 轮工作结束，休息 %d 分钟。" % (self._round, self._pomodoro["break_min"]))
                self._phase = PHASE_BREAK
                self._phase_end = self._phase_end + timedelta(minutes=self._pomodoro["break_min"])
            else:  # PHASE_BREAK
                self._round += 1
                last_msg = ("休息结束", "开始第 %d 轮工作（%d 分钟）。" % (self._round, self._pomodoro["work_min"]))
                self._phase = PHASE_WORK
                self._phase_end = self._phase_end + timedelta(minutes=self._pomodoro["work_min"])
        if last_msg is None:
            return []
        return [{"kind": "pomodoro", "title": last_msg[0], "message": last_msg[1]}]
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_reminder.py -v`
Expected: 全部 PASS（含 Task 2 的测试）。

- [ ] **Step 5: 提交**

```bash
git add reminder.py tests/test_reminder.py
git commit -m "feat(reminder): add pomodoro state machine with catch-up coalescing"
```

---

## Task 4: reminder.py 一次性/每日检测 + arm

**Files:**
- Modify: `reminder.py`
- Test: `tests/test_reminder.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_reminder.py` 末尾追加：

```python
def test_oneshot_fires_once_and_is_removed():
    s = ReminderScheduler()
    s.arm(datetime(2026, 8, 2, 19, 0))
    s.add_oneshot("开会", datetime(2026, 8, 2, 20, 0))
    assert s.tick(datetime(2026, 8, 2, 19, 59)) == []
    ev = s.tick(datetime(2026, 8, 2, 20, 0))
    assert len(ev) == 1 and ev[0]["kind"] == "oneshot" and ev[0]["message"] == "开会"
    assert s.tick(datetime(2026, 8, 2, 20, 1)) == []   # 已移除，不再触发
    assert s.list_reminders()[0] == []


def test_oneshot_overdue_at_startup_fires_on_first_tick():
    s = ReminderScheduler()
    s.add_oneshot("开会", datetime(2026, 8, 2, 20, 0))
    s.arm(datetime(2026, 8, 2, 21, 0))                # 启动时已过期
    ev = s.tick(datetime(2026, 8, 2, 21, 0))
    assert len(ev) == 1 and ev[0]["message"] == "开会"


def test_daily_fires_on_crossing_not_repeated():
    s = ReminderScheduler()
    s.add_daily("喝水", 8, 0)
    s.arm(datetime(2026, 8, 2, 7, 0))
    assert s.tick(datetime(2026, 8, 2, 7, 59)) == []
    ev = s.tick(datetime(2026, 8, 2, 8, 0, 30))
    assert len(ev) == 1 and ev[0]["kind"] == "daily" and ev[0]["message"] == "喝水"
    assert s.tick(datetime(2026, 8, 2, 8, 1)) == []   # 不重复


def test_daily_not_retrofired_before_arm_time():
    s = ReminderScheduler()
    s.add_daily("喝水", 8, 0)
    s.arm(datetime(2026, 8, 2, 9, 0))                 # 9 点才启动
    assert s.tick(datetime(2026, 8, 2, 9, 0)) == []   # 不补发 8 点


def test_daily_sleep_wake_catchup_fires_once():
    s = ReminderScheduler()
    s.add_daily("喝水", 8, 0)
    s.arm(datetime(2026, 8, 2, 7, 0))
    s.tick(datetime(2026, 8, 2, 7, 30))
    ev = s.tick(datetime(2026, 8, 2, 9, 0))           # 休眠后唤醒，已过 8 点
    assert len(ev) == 1 and ev[0]["message"] == "喝水"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_reminder.py -v -k "oneshot or daily"`
Expected: FAIL（`ReminderScheduler` 无 `arm`，`tick` 不处理一次性/每日）。

- [ ] **Step 3: 实现 arm + 一次性/每日检测**

在 `ReminderScheduler` 的 `tick` 方法之前插入 `arm`：

```python
    def arm(self, now=None):
        """启动时调用一次：设 _last_tick = now，使每日提醒不补发启动前已过时刻。"""
        self._last_tick = now or self._now_fn()
```

把 `tick` 方法体改为同时调用三类检测：

```python
    def tick(self, now=None):
        """推进状态，返回到期事件列表。事件形如 {"kind","title","message"}。"""
        now = now or self._now_fn()
        events = []
        try:
            events.extend(self._tick_pomodoro(now))
            events.extend(self._tick_oneshot(now))
            events.extend(self._tick_daily(now))
        finally:
            self._last_tick = now
        return events
```

在 `_tick_pomodoro` 之后追加两个私有方法：

```python
    def _tick_oneshot(self, now):
        events = []
        remaining = []
        for e in self._oneshot:
            try:
                fired = now >= datetime.fromisoformat(e["when"])
            except (ValueError, TypeError):
                fired = False
            if fired:
                events.append({"kind": "oneshot", "title": "提醒", "message": e["label"]})
            else:
                remaining.append(e)
        self._oneshot = remaining
        return events

    def _tick_daily(self, now):
        events = []
        if self._last_tick is None:
            return events
        for e in self._daily:
            try:
                occ = now.replace(hour=e["hour"], minute=e["minute"], second=0, microsecond=0)
            except (ValueError, TypeError):
                continue
            if self._last_tick < occ <= now:
                events.append({"kind": "daily", "title": "每日提醒", "message": e["label"]})
        return events
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_reminder.py -v`
Expected: 全部 PASS。

- [ ] **Step 5: 提交**

```bash
git add reminder.py tests/test_reminder.py
git commit -m "feat(reminder): add one-shot/daily detection with arm and missed-policy"
```

---

## Task 5: notify.py（resolve_sound 纯函数 + notify 胶水）

**Files:**
- Create: `notify.py`
- Test: `tests/test_notify.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_notify.py`：

```python
import notify


def test_resolve_sound_system_mode():
    assert notify.resolve_sound({"mode": "system", "path": ""}) == ("system", None)


def test_resolve_sound_missing_mode():
    assert notify.resolve_sound({"path": "C:/a.wav"}) == ("system", None)


def test_resolve_sound_custom_with_existing_file(tmp_path):
    f = tmp_path / "a.wav"
    f.write_bytes(b"RIFF")
    assert notify.resolve_sound({"mode": "custom", "path": str(f)}) == ("custom", str(f))


def test_resolve_sound_custom_missing_file_falls_back():
    assert notify.resolve_sound({"mode": "custom", "path": "C:/nope.wav"}) == ("system", None)


def test_resolve_sound_custom_empty_path_falls_back():
    assert notify.resolve_sound({"mode": "custom", "path": ""}) == ("system", None)


def test_resolve_sound_non_dict_cfg():
    assert notify.resolve_sound(None) == ("system", None)
    assert notify.resolve_sound("junk") == ("system", None)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_notify.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'notify'`）。

- [ ] **Step 3: 实现 notify.py**

创建 `notify.py`：

```python
"""提醒通知：唤回窗口 + 提示音 + 模态弹框。薄 UI 胶水。"""

import os
import sys
from tkinter import messagebox


def resolve_sound(sound_cfg):
    """纯函数：决定播放哪种提示音。

    返回 ("custom", path) 或 ("system", None)。
    mode == "custom" 且 path 非空且文件存在 -> custom；否则 system。
    """
    if not isinstance(sound_cfg, dict):
        return ("system", None)
    if sound_cfg.get("mode") != "custom":
        return ("system", None)
    path = sound_cfg.get("path")
    if isinstance(path, str) and path and os.path.isfile(path):
        return ("custom", path)
    return ("system", None)


def _play_sound(sound_cfg, root):
    kind, path = resolve_sound(sound_cfg)
    try:
        if sys.platform == "win32":
            import winsound
            if kind == "custom":
                winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
            else:
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            return
    except Exception:
        pass
    try:
        root.bell()
    except Exception:
        pass


def notify(root, title, message, sound_cfg=None):
    """唤回主窗口、播放提示音、弹模态框。任何失败都不阻断弹框。"""
    try:
        root.deiconify()
        root.lift()
        root.focus_force()
    except Exception:
        pass
    _play_sound(sound_cfg, root)
    messagebox.showinfo(title, message)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_notify.py -v`
Expected: 全部 PASS。

- [ ] **Step 5: 提交**

```bash
git add notify.py tests/test_notify.py
git commit -m "feat(notify): add sound resolution and notify helper"
```

---

## Task 6: reminder_dialog.py 管理对话框

**Files:**
- Create: `reminder_dialog.py`
- Test: `tests/test_reminder_dialog.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_reminder_dialog.py`：

```python
import reminder
from reminder_dialog import ReminderDialog


def test_dialog_lists_and_deletes(tk_root):
    sched = reminder.ReminderScheduler()
    dlg = ReminderDialog(tk_root, sched, {"mode": "system", "path": ""}, on_change=lambda: None)
    try:
        e = sched.add_daily("喝水", 8, 0)
        dlg.refresh_list()
        assert len(dlg._tree.get_children()) == 1
        sched.remove(e["id"])
        dlg.refresh_list()
        assert len(dlg._tree.get_children()) == 0
    finally:
        dlg.destroy()


def test_dialog_sound_config(tk_root):
    sched = reminder.ReminderScheduler()
    dlg = ReminderDialog(tk_root, sched, {"mode": "custom", "path": "C:/x.wav"}, on_change=lambda: None)
    try:
        cfg = dlg.sound_config()
        assert cfg == {"mode": "custom", "path": "C:/x.wav"}
    finally:
        dlg.destroy()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_reminder_dialog.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'reminder_dialog'`）；无显示器环境下 SKIP。

- [ ] **Step 3: 实现 reminder_dialog.py**

创建 `reminder_dialog.py`：

```python
"""ReminderDialog：提醒管理对话框（非模态 Toplevel）。"""

import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk

import notify


class ReminderDialog(tk.Toplevel):
    def __init__(self, master, scheduler, sound_cfg, on_change):
        super().__init__(master)
        self.title("提醒管理")
        self._scheduler = scheduler
        self._on_change = on_change
        self._sound_cfg = dict(sound_cfg) if isinstance(sound_cfg, dict) else {"mode": "system", "path": ""}
        self._build_pomodoro()
        self._build_list()
        self._build_add()
        self._build_sound()
        self.refresh_list()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---- 番茄钟 ----
    def _build_pomodoro(self):
        frame = ttk.LabelFrame(self, text="番茄钟")
        frame.pack(fill=tk.X, padx=6, pady=4)
        cfg = self._scheduler.pomodoro_config()
        self._work_var = tk.IntVar(value=cfg["work_min"])
        self._break_var = tk.IntVar(value=cfg["break_min"])
        self._rounds_var = tk.IntVar(value=cfg["rounds"])
        ttk.Label(frame, text="工作(分)").pack(side=tk.LEFT, padx=2)
        ttk.Spinbox(frame, from_=1, to=180, width=4, textvariable=self._work_var).pack(side=tk.LEFT)
        ttk.Label(frame, text="休息(分)").pack(side=tk.LEFT, padx=2)
        ttk.Spinbox(frame, from_=1, to=180, width=4, textvariable=self._break_var).pack(side=tk.LEFT)
        ttk.Label(frame, text="轮数").pack(side=tk.LEFT, padx=2)
        ttk.Spinbox(frame, from_=1, to=12, width=4, textvariable=self._rounds_var).pack(side=tk.LEFT)
        self._pomo_btn = ttk.Button(frame, text="开始", width=6, command=self._on_pomo_toggle)
        self._pomo_btn.pack(side=tk.LEFT, padx=6)
        self._pomo_status = ttk.Label(frame, text="")
        self._pomo_status.pack(side=tk.LEFT, padx=4)

    def _apply_pomodoro_cfg(self):
        try:
            cfg = {
                "work_min": self._work_var.get(),
                "break_min": self._break_var.get(),
                "rounds": self._rounds_var.get(),
            }
        except tk.TclError:
            return
        self._scheduler.update_pomodoro(cfg)

    def _on_pomo_toggle(self):
        self._apply_pomodoro_cfg()
        if self._scheduler.pomodoro_phase() == "idle":
            self._scheduler.start_pomodoro()
        else:
            self._scheduler.stop_pomodoro()
        self.refresh_status()
        self._on_change()

    def refresh_status(self):
        running = self._scheduler.pomodoro_phase() != "idle"
        self._pomo_btn.configure(text="停止" if running else "开始")
        rem = self._scheduler.pomodoro_remaining()
        self._pomo_status.configure(text=("%s %s %s" % rem) if rem else "")

    # ---- 列表 ----
    def _build_list(self):
        frame = ttk.LabelFrame(self, text="提醒列表")
        frame.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)
        self._tree = ttk.Treeview(frame, columns=("type", "label", "when"), show="headings", height=6)
        self._tree.heading("type", text="类型")
        self._tree.heading("label", text="内容")
        self._tree.heading("when", text="时间")
        self._tree.column("type", width=60)
        self._tree.column("label", width=140)
        self._tree.column("when", width=140)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        ttk.Button(frame, text="删除选中", command=self._on_delete).pack(side=tk.RIGHT, padx=4)

    def refresh_list(self):
        for item in self._tree.get_children():
            self._tree.delete(item)
        oneshot, daily = self._scheduler.list_reminders()
        for e in oneshot:
            self._tree.insert("", tk.END, iid=e["id"], values=("一次性", e["label"], e["when"].replace("T", " ")))
        for e in daily:
            self._tree.insert("", tk.END, iid=e["id"], values=("每日", e["label"], "每天 %02d:%02d" % (e["hour"], e["minute"])))
        self.refresh_status()

    def _on_delete(self):
        sel = self._tree.selection()
        if not sel:
            return
        for rid in sel:
            self._scheduler.remove(rid)
        self.refresh_list()
        self._on_change()

    # ---- 新增 ----
    def _build_add(self):
        frame = ttk.LabelFrame(self, text="新增提醒（每日忽略日期）")
        frame.pack(fill=tk.X, padx=6, pady=4)
        ttk.Label(frame, text="内容").pack(side=tk.LEFT, padx=2)
        self._label_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self._label_var, width=12).pack(side=tk.LEFT)
        self._type_var = tk.StringVar(value="daily")
        ttk.Radiobutton(frame, text="每日", value="daily", variable=self._type_var).pack(side=tk.LEFT, padx=4)
        ttk.Radiobutton(frame, text="一次性", value="oneshot", variable=self._type_var).pack(side=tk.LEFT, padx=4)
        self._date_var = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
        ttk.Label(frame, text="日期").pack(side=tk.LEFT, padx=2)
        ttk.Entry(frame, textvariable=self._date_var, width=10).pack(side=tk.LEFT)
        self._hour_var = tk.IntVar(value=datetime.now().hour)
        self._minute_var = tk.IntVar(value=0)
        ttk.Label(frame, text="时").pack(side=tk.LEFT, padx=2)
        ttk.Spinbox(frame, from_=0, to=23, width=3, textvariable=self._hour_var).pack(side=tk.LEFT)
        ttk.Label(frame, text="分").pack(side=tk.LEFT, padx=2)
        ttk.Spinbox(frame, from_=0, to=59, width=3, textvariable=self._minute_var).pack(side=tk.LEFT)
        ttk.Button(frame, text="添加", command=self._on_add).pack(side=tk.LEFT, padx=6)

    def _on_add(self):
        label = self._label_var.get().strip()
        if not label:
            messagebox.showwarning("新增提醒", "请填写内容。", parent=self)
            return
        try:
            hour = self._hour_var.get()
            minute = self._minute_var.get()
        except tk.TclError:
            messagebox.showwarning("新增提醒", "时间格式不正确。", parent=self)
            return
        if self._type_var.get() == "daily":
            self._scheduler.add_daily(label, hour, minute)
        else:
            try:
                when = datetime.strptime("%s %02d:%02d" % (self._date_var.get().strip(), hour, minute), "%Y-%m-%d %H:%M")
            except ValueError:
                messagebox.showwarning("新增提醒", "日期格式应为 YYYY-MM-DD。", parent=self)
                return
            self._scheduler.add_oneshot(label, when)
        self._label_var.set("")
        self.refresh_list()
        self._on_change()

    # ---- 提示音 ----
    def _build_sound(self):
        frame = ttk.LabelFrame(self, text="提示音")
        frame.pack(fill=tk.X, padx=6, pady=4)
        self._sound_mode_var = tk.StringVar(value=self._sound_cfg.get("mode", "system"))
        ttk.Radiobutton(frame, text="系统提示音", value="system", variable=self._sound_mode_var, command=self._on_sound_change).pack(side=tk.LEFT, padx=4)
        ttk.Radiobutton(frame, text="自定义音频", value="custom", variable=self._sound_mode_var, command=self._on_sound_change).pack(side=tk.LEFT, padx=4)
        self._sound_path_var = tk.StringVar(value=self._sound_cfg.get("path", ""))
        ttk.Entry(frame, textvariable=self._sound_path_var, width=24).pack(side=tk.LEFT, padx=4)
        ttk.Button(frame, text="浏览...", width=6, command=self._on_browse).pack(side=tk.LEFT)
        ttk.Button(frame, text="试听", width=4, command=self._on_preview).pack(side=tk.LEFT, padx=4)

    def _on_browse(self):
        path = filedialog.askopenfilename(
            title="选择音频文件", filetypes=[("Wave 音频", "*.wav"), ("所有文件", "*.*")], parent=self
        )
        if path:
            self._sound_path_var.set(path)
            self._sound_mode_var.set("custom")
            self._on_sound_change()

    def _on_preview(self):
        notify.notify(self, "试听", "提示音试听", self.sound_config())

    def _on_sound_change(self):
        self._sound_cfg = self.sound_config()
        self._on_change()

    def sound_config(self):
        return {"mode": self._sound_mode_var.get(), "path": self._sound_path_var.get().strip()}

    def _on_close(self):
        self._on_change()
        self.destroy()
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_reminder_dialog.py -v`
Expected: 有显示器则 PASS；无显示器则 SKIP（`tk_root` fixture）。

- [ ] **Step 5: 提交**

```bash
git add reminder_dialog.py tests/test_reminder_dialog.py
git commit -m "feat(reminder): add management dialog with pomodoro, list and sound config"
```

---

## Task 7: app.py 接线

**Files:**
- Modify: `app.py`
- Test: 手动验证（仓库无 app.py 自动测试，NoteApp 会启动托盘/after 循环，不适合无显示器单测）

- [ ] **Step 1: 增加导入**

把 `app.py` 顶部导入区改为（新增 `sys`、`datetime`、`notify`、`ReminderScheduler`、`ReminderDialog`）：

```python
import os
import sys
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox

import snote
import settings
import notify
from editor import RichTextEditor
from reminder import ReminderScheduler
from reminder_dialog import ReminderDialog
from tray import TrayController
from notes_panel import NotesPanel
from toolbar import FormatToolbar
```

- [ ] **Step 2: 在 __init__ 中创建调度器并启动 tick 循环**

在 `__init__` 里 `self._ls_var = tk.StringVar(value=self._line_spacing)` 之后插入：

```python
        self.scheduler = ReminderScheduler()
        self.scheduler.load_dict(self.settings.get("pomodoro"), self.settings.get("reminders"))
        self._sound_cfg = self.settings.get("sound") or dict(settings.DEFAULT_SOUND)
        self._reminder_dlg = None
        self.scheduler.arm(datetime.now())
```

在 `__init__` 末尾 `self.root.protocol("WM_DELETE_WINDOW", self._on_close)` 之后插入：

```python
        self._tick()
```

- [ ] **Step 3: 在 _build_menu 中加入「提醒」菜单**

在 `_build_menu` 中 `menubar.add_cascade(label="查看", menu=view_menu)` 之后、`help_menu` 之前插入：

```python
        remind_menu = tk.Menu(menubar, tearoff=0)
        remind_menu.add_command(label="管理提醒...", command=self._open_reminder_dialog)
        remind_menu.add_separator()
        remind_menu.add_command(label="开始番茄钟", command=self._start_pomodoro)
        remind_menu.add_command(label="停止番茄钟", command=self._stop_pomodoro)
        menubar.add_cascade(label="提醒", menu=remind_menu)
```

- [ ] **Step 4: 增加提醒相关方法**

在 `_on_line_spacing` 方法之后插入：

```python
    # ---- 提醒 ----
    def _tick(self):
        try:
            now = datetime.now()
            events = self.scheduler.tick(now)
            for ev in events:
                notify.notify(self.root, ev["title"], ev["message"], self._sound_cfg)
            if events:
                self._persist()
            self._refresh_title(now)
            if self._reminder_dlg is not None and self._reminder_dlg.winfo_exists():
                self._reminder_dlg.refresh_status()
        except Exception as exc:
            print("warning: reminder tick error: %s" % exc, file=sys.stderr)
        finally:
            self.root.after(1000, self._tick)

    def _refresh_title(self, now=None):
        rem = self.scheduler.pomodoro_remaining(now)
        if rem is None:
            self.root.title("Simple Note")
        else:
            self.root.title("Simple Note — %s %s（%s）" % rem)

    def _persist(self):
        pomodoro, reminders = self.scheduler.to_dict()
        self.settings["pomodoro"] = pomodoro
        self.settings["reminders"] = reminders
        if self._reminder_dlg is not None and self._reminder_dlg.winfo_exists():
            self._sound_cfg = self._reminder_dlg.sound_config()
        self.settings["sound"] = self._sound_cfg
        settings.save_settings(self.settings)

    def _on_reminder_change(self):
        self._persist()
        self._refresh_title()

    def _open_reminder_dialog(self):
        if self._reminder_dlg is not None and self._reminder_dlg.winfo_exists():
            self._reminder_dlg.lift()
            return
        self._reminder_dlg = ReminderDialog(
            self.root, self.scheduler, self._sound_cfg, on_change=self._on_reminder_change
        )

    def _start_pomodoro(self):
        self.scheduler.start_pomodoro(datetime.now())
        self._refresh_title()

    def _stop_pomodoro(self):
        self.scheduler.stop_pomodoro()
        self._refresh_title()
```

- [ ] **Step 5: 退出前持久化**

把 `_real_quit` 改为在 `self.tray.stop()` 之前先 `self._persist()`：

```python
    def _real_quit(self):
        for doc in list(self.docs):
            if doc.dirty:
                self.switch_to(doc)
                if not self._confirm_save(doc):
                    return
        self._persist()
        self.tray.stop()
        self.root.destroy()
```

- [ ] **Step 6: 跑全部自动测试确认无回归**

Run: `uv run pytest`
Expected: 既有测试 + 新增 test_settings/test_reminder/test_notify 全 PASS；test_editor/test_reminder_dialog 在无显示器时 SKIP（检查 skipped 计数）。

- [ ] **Step 7: 手动验证（有显示器/Windows）**

Run: `uv run python main.py`
逐项确认：
1. 菜单栏出现「提醒」→「管理提醒...」打开非模态对话框，可同时编辑笔记。
2. 番茄钟：设工作 1 分钟、休息 1 分钟、轮数 1，点「开始」→ 标题栏出现「工作中 01:00（第1/共1轮）」倒计时；到点弹模态框+提示音；完成后标题还原「Simple Note」。
3. 每日提醒：添加「喝水」每天当前时刻+1 分钟 → 到点弹框。
4. 一次性提醒：添加当前日期、当前时刻+1 分钟 → 到点弹框后从列表消失。
5. 提示音：选「自定义音频」→ 浏览选一个 .wav → 试听有声；重启应用后设置仍在。
6. 最小化到托盘后触发提醒 → 窗口被唤回并弹框。
7. 重启应用 → 每日提醒与番茄钟时长偏好仍在；运行中的番茄钟不恢复（符合设计）。

- [ ] **Step 8: 提交**

```bash
git add app.py
git commit -m "feat(app): wire reminder scheduler, menu, title countdown and persistence"
```

---

## Task 8: 更新 AGENTS.md

**Files:**
- Modify: `AGENTS.md`

- [ ] **Step 1: 更新测试清单（Environment gotchas 段）**

把 AGENTS.md 中这句：

```
`test_util`, `test_snote`, `test_settings`, and `test_tray` are headless-safe (no real Tk — `test_tray` drives a `_FakeRoot`); only `test_editor` needs a display.
```

改为：

```
`test_util`, `test_snote`, `test_settings`, `test_notify`, `test_reminder`, and `test_tray` are headless-safe (no real Tk — `test_tray` drives a `_FakeRoot`, `test_reminder`/`test_notify` are pure logic with an injected clock); `test_editor` and `test_reminder_dialog` need a display.
```

- [ ] **Step 2: 在 Architecture 段补充三个新模块**

在 `settings.py` 那条 bullet 之后追加：

```
- `reminder.py` — Tk-free 提醒调度引擎（番茄钟状态机 + 一次性/每日提醒），时钟经 `now_fn` 注入故可无显示器单测。由 `app.NoteApp` 用 `root.after(1000, _tick)` 每秒在主线程驱动；`tick(now)` 返回到期事件。番茄钟追赶（休眠唤醒）会静默推进、每次 tick 只发一条通知。每日提醒用 `_last_tick < occ <= now` 检测跨过；`arm(now)` 在启动时设定基准，使启动前已过的每日提醒不补发。
- `notify.py` — 通知胶水：`resolve_sound(cfg)` 纯函数（custom .wav 存在则自定义，否则系统蜂鸣）+ `notify(root, title, msg, sound_cfg)`（唤回窗口→winsound 播音→模态 `messagebox`）。自定义音频仅 Windows/.wav（`winsound.PlaySound`），任何失败回退 `root.bell()`，绝不阻断弹框。
- `reminder_dialog.py` — 非模态管理对话框 `ReminderDialog(tk.Toplevel)`：番茄钟启停/参数、提醒列表增删、提示音配置（`sound_config()` 取回）。经 `on_change` 回调触发 app 持久化。
```

- [ ] **Step 3: 在 Conventions 段补充持久化与线程约定**

在 Conventions 段末尾追加：

```
- 提醒数据持久化在 `settings.json` 的 `sound`/`pomodoro`/`reminders` 键；`settings.py` 只做容错读写（保留 dict 形值），深度清洗在 `reminder.ReminderScheduler.load_dict`。
- 提醒/番茄钟全程跑在 Tk 主线程（`root.after`），切勿引入后台线程；`app._tick` 必须异常安全且无论如何都重新 `after`，否则提醒会静默停摆。
```

- [ ] **Step 4: 提交**

```bash
git add AGENTS.md
git commit -m "docs: document reminder/notify/dialog modules and test lists"
```

---

## 完成校验

- [ ] 跑 `uv run pytest` 全绿（核对 skipped 计数符合预期：无显示器时 test_editor / test_reminder_dialog 跳过）。
- [ ] 手动验证清单（Task 7 Step 7）全部通过。
- [ ] `git log --oneline` 确认 8 个任务各自成提交。
