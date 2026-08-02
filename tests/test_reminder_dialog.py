import reminder
from datetime import datetime
from reminder_dialog import ReminderDialog, _valid_hhmm


class _FakeDT:
    NOW = datetime(2026, 8, 2, 12, 0)

    @classmethod
    def now(cls):
        return cls.NOW

    @classmethod
    def strptime(cls, s, fmt):
        return datetime.strptime(s, fmt)


class _FakeRoot:
    def __init__(self):
        self.titles = []

    def title(self, t=None):
        if t is not None:
            self.titles.append(t)
        return "Simple Note"


def test_valid_hhmm_ranges():
    assert _valid_hhmm(0, 0) is True
    assert _valid_hhmm(23, 59) is True
    assert _valid_hhmm(24, 0) is False
    assert _valid_hhmm(0, 60) is False
    assert _valid_hhmm(-1, 0) is False


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


def test_dialog_close_applies_pomodoro_cfg(tk_root):
    sched = reminder.ReminderScheduler()
    dlg = ReminderDialog(tk_root, sched, {"mode": "system", "path": ""}, on_change=lambda: None)
    dlg._work_var.set(50)
    dlg._on_close()   # 关闭即销毁，作为最后一步
    assert sched.pomodoro_config()["work_min"] == 50


def test_apply_pomodoro_cfg_invalid_returns_false(tk_root):
    sched = reminder.ReminderScheduler()
    dlg = ReminderDialog(tk_root, sched, {"mode": "system", "path": ""}, on_change=lambda: None)
    try:
        before = sched.pomodoro_config()
        dlg._work_var.set("abc")
        assert dlg._apply_pomodoro_cfg() is False
        assert sched.pomodoro_config() == before  # 非法输入不落盘
    finally:
        dlg.destroy()


def test_apply_pomodoro_cfg_valid_returns_true(tk_root):
    sched = reminder.ReminderScheduler()
    dlg = ReminderDialog(tk_root, sched, {"mode": "system", "path": ""}, on_change=lambda: None)
    try:
        dlg._work_var.set(50)
        dlg._break_var.set(10)
        dlg._rounds_var.set(3)
        assert dlg._apply_pomodoro_cfg() is True
        cfg = sched.pomodoro_config()
        assert (cfg["work_min"], cfg["break_min"], cfg["rounds"]) == (50, 10, 3)
    finally:
        dlg.destroy()


def test_apply_pomodoro_cfg_clamps_and_writes_back_vars(tk_root):
    sched = reminder.ReminderScheduler()
    dlg = ReminderDialog(tk_root, sched, {"mode": "system", "path": ""}, on_change=lambda: None)
    try:
        dlg._work_var.set(500)
        dlg._break_var.set(0)
        dlg._rounds_var.set(99)
        assert dlg._apply_pomodoro_cfg() is True
        cfg = sched.pomodoro_config()
        assert (cfg["work_min"], cfg["break_min"], cfg["rounds"]) == (180, 1, 12)
        assert (dlg._work_var.get(), dlg._break_var.get(), dlg._rounds_var.get()) == (180, 1, 12)
    finally:
        dlg.destroy()


def test_on_pomo_toggle_invalid_cfg_shows_warning(tk_root, monkeypatch):
    sched = reminder.ReminderScheduler()
    calls = []
    dlg = ReminderDialog(tk_root, sched, {"mode": "system", "path": ""}, on_change=lambda: calls.append(1))
    warns = []
    monkeypatch.setattr("reminder_dialog.messagebox.showwarning", lambda *a, **k: warns.append(a))
    try:
        dlg._work_var.set("abc")
        dlg._on_pomo_toggle()
        assert warns == [("番茄钟", "参数格式不正确。")]
        assert sched.pomodoro_phase() == "idle"  # 未 start/stop
        assert calls == [], "非法输入不应触发持久化"
    finally:
        dlg.destroy()


def test_on_add_rejects_past_oneshot(tk_root, monkeypatch):
    sched = reminder.ReminderScheduler()
    calls = []
    dlg = ReminderDialog(tk_root, sched, {"mode": "system", "path": ""}, on_change=lambda: calls.append(1))
    warns = []
    monkeypatch.setattr("reminder_dialog.messagebox.showwarning", lambda *a, **k: warns.append(a))
    monkeypatch.setattr("reminder_dialog.datetime", _FakeDT)
    try:
        dlg._label_var.set("过去")
        dlg._type_var.set("oneshot")
        dlg._date_var.set("2026-08-02")
        dlg._hour_var.set(11)
        dlg._minute_var.set(30)
        dlg._on_add()
        assert warns == [("新增提醒", "时间必须晚于当前。")]
        assert sched.list_reminders() == ([], [])  # 未新增
        assert calls == []  # _on_change 未被调用
    finally:
        dlg.destroy()


def test_on_add_surfaces_add_valueerror(tk_root, monkeypatch):
    sched = reminder.ReminderScheduler()
    dlg = ReminderDialog(tk_root, sched, {"mode": "system", "path": ""}, on_change=lambda: None)
    warns = []
    monkeypatch.setattr("reminder_dialog.messagebox.showwarning", lambda *a, **k: warns.append(a))
    monkeypatch.setattr("reminder_dialog.datetime", _FakeDT)

    def boom(*a, **k):
        raise ValueError("引擎拒绝")

    monkeypatch.setattr(sched, "add_oneshot", boom)
    try:
        dlg._label_var.set("未来")
        dlg._type_var.set("oneshot")
        dlg._date_var.set("2026-08-03")
        dlg._hour_var.set(12)
        dlg._minute_var.set(30)
        dlg._on_add()
        assert warns == [("新增提醒", "引擎拒绝")]
        assert sched.list_reminders() == ([], [])
    finally:
        dlg.destroy()


def test_on_delete_requires_confirmation(tk_root, monkeypatch):
    sched = reminder.ReminderScheduler()
    dlg = ReminderDialog(tk_root, sched, {"mode": "system", "path": ""}, on_change=lambda: None)
    answers = iter([False, True])
    monkeypatch.setattr("reminder_dialog.messagebox.askyesno", lambda *a, **k: next(answers))
    try:
        e = sched.add_daily("喝水", 8, 0)
        dlg.refresh_list()
        dlg._tree.selection_set(e["id"])
        dlg._on_delete()
        assert sched.list_reminders()[1]  # 拒绝后仍存在
        dlg._on_delete()
        assert sched.list_reminders()[1] == []  # 确认后删除
    finally:
        dlg.destroy()


def test_app_start_pomodoro_noop_when_running():
    from app import NoteApp

    app = NoteApp.__new__(NoteApp)
    sched = reminder.ReminderScheduler()
    root = _FakeRoot()
    app.scheduler, app.root = sched, root
    app._title_cache = None
    sched.start_pomodoro(datetime(2026, 8, 2, 10, 0))
    phase_before = sched.pomodoro_phase()
    end_before = sched._phase_end
    app._start_pomodoro()
    assert sched.pomodoro_phase() == phase_before  # 不重置进行中的会话
    assert sched._phase_end == end_before
    assert root.titles == []  # 提前 return，未刷标题


def test_app_start_pomodoro_idle_starts():
    from app import NoteApp

    app = NoteApp.__new__(NoteApp)
    sched = reminder.ReminderScheduler()
    app.scheduler, app.root = sched, _FakeRoot()
    app._title_cache = None
    app._start_pomodoro()
    assert sched.pomodoro_phase() == reminder.PHASE_WORK


def test_refresh_title_caches_unchanged_title():
    from app import NoteApp

    app = NoteApp.__new__(NoteApp)
    sched = reminder.ReminderScheduler()
    root = _FakeRoot()
    app.scheduler, app.root = sched, root
    app._title_cache = None
    now = datetime(2026, 8, 2, 10, 0)
    app._refresh_title(now)
    app._refresh_title(now)
    app._refresh_title(now)
    assert root.titles == ["Simple Note"]  # 未变化不重设
    sched.start_pomodoro(now)
    app._refresh_title(now)
    app._refresh_title(now)
    assert len(root.titles) == 2  # 标题变化时仅设一次
    assert root.titles[1] == "Simple Note — 工作中 25:00（第1/共4轮）"
