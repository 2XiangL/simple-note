from datetime import datetime, timedelta

import pytest

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


def test_add_daily_rejects_out_of_range():
    s = ReminderScheduler()
    with pytest.raises(ValueError):
        s.add_daily("x", 99, 0)
    with pytest.raises(ValueError):
        s.add_daily("x", 8, 60)
    with pytest.raises(ValueError):
        s.add_daily("x", -1, 0)
    with pytest.raises(ValueError):
        s.add_daily("x", "abc", 0)
    with pytest.raises(ValueError):
        s.add_daily("", 8, 0)
    with pytest.raises(ValueError):
        s.add_daily("  ", 8, 0)
    with pytest.raises(ValueError):
        s.add_daily(123, 8, 0)
    _, daily = s.list_reminders()
    assert daily == []   # 非法输入不产生残留


def test_add_daily_accepts_numeric_strings():
    s = ReminderScheduler()
    s.add_daily("喝水", "8", "0")   # 与加载器 int() 行为一致
    _, daily = s.list_reminders()
    assert daily[0]["hour"] == 8 and daily[0]["minute"] == 0


def test_add_oneshot_rejects_nondatetime():
    s = ReminderScheduler()
    with pytest.raises(ValueError):
        s.add_oneshot("x", "tomorrow")
    with pytest.raises(ValueError):
        s.add_oneshot("x", None)
    with pytest.raises(ValueError):
        s.add_oneshot("", datetime(2026, 8, 2, 20, 0))
    _, oneshot = s.list_reminders()
    assert oneshot == []   # 非法输入不产生残留


def test_load_dict_dedupes_ids():
    s = ReminderScheduler()
    dup = {"daily": [
        {"id": "a", "label": "一", "hour": 9, "minute": 0},
        {"id": "a", "label": "二", "hour": 10, "minute": 0},
    ]}
    s.load_dict(None, dup)
    _, daily = s.list_reminders()
    assert len(daily) == 1, "重复 ID 未去重"
    assert daily[0]["label"] == "一"   # 保留先出现者


def test_load_dict_dedupes_across_oneshot_and_daily():
    s = ReminderScheduler()
    s.load_dict(
        None,
        {
            "oneshot": [{"id": "a", "label": "一次性", "when": "2026-08-02T20:00:00"}],
            "daily": [{"id": "a", "label": "每日", "hour": 8, "minute": 0}],
        },
    )
    oneshot, daily = s.list_reminders()
    assert len(oneshot) == 1 and oneshot[0]["label"] == "一次性"
    assert daily == []   # 同 id 在两类中各一条时保留先出现者（oneshot）


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


def test_sanitize_pomodoro_inf_does_not_raise():
    assert reminder.sanitize_pomodoro({"work_min": 1e999}) == {"work_min": 25, "break_min": 5, "rounds": 4}


def test_load_dict_drops_daily_with_inf_hour():
    s = ReminderScheduler()
    s.load_dict(
        {"work_min": 25, "break_min": 5, "rounds": 4},
        {"daily": [{"id": "x", "label": "ok", "hour": 1e999, "minute": 0}]},
    )
    _, daily = s.list_reminders()
    assert daily == []


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


def test_pomodoro_tick_without_boundary_returns_empty():
    t0 = datetime(2026, 8, 2, 9, 0)
    s = ReminderScheduler()
    s.update_pomodoro({"work_min": 25, "break_min": 5, "rounds": 4})
    s.start_pomodoro(t0)
    assert s.tick(t0 + timedelta(minutes=10)) == []   # 未跨阶段边界


def test_pomodoro_remaining_clamps_negative_to_zero():
    t0 = datetime(2026, 8, 2, 9, 0)
    s = ReminderScheduler()
    s.update_pomodoro({"work_min": 25, "break_min": 5, "rounds": 4})
    s.start_pomodoro(t0)
    # 已过时点 -> 剩余 00:00 而非负数
    assert s.pomodoro_remaining(t0 + timedelta(minutes=40)) == ("工作中", "00:00", "第1/共4轮")


def test_pomodoro_phase_transition_messages():
    t0 = datetime(2026, 8, 2, 9, 0)
    s = ReminderScheduler()
    s.update_pomodoro({"work_min": 25, "break_min": 5, "rounds": 2})
    s.start_pomodoro(t0)
    ev = s.tick(t0 + timedelta(minutes=25))
    assert ev[0]["title"] == "工作结束" and "休息" in ev[0]["message"]
    ev = s.tick(t0 + timedelta(minutes=30))
    assert ev[0]["title"] == "休息结束" and "第 2 轮" in ev[0]["message"]
    # 第2轮工作的剩余标签为 第2/共2轮
    assert s.pomodoro_remaining(t0 + timedelta(minutes=30)) == ("工作中", "25:00", "第2/共2轮")


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


def test_add_oneshot_tzaware_normalized_to_naive():
    from datetime import timezone
    s = ReminderScheduler()
    aware = datetime(2026, 8, 2, 20, 0, tzinfo=timezone(timedelta(hours=8)))
    s.add_oneshot("开会", aware)
    e = s.list_reminders()[0][0]
    assert e["when"] == "2026-08-02T20:00:00"   # 已归一化为 naive，不含偏移


def test_add_oneshot_tzaware_still_fires():
    from datetime import timezone
    s = ReminderScheduler()
    aware = datetime(2026, 8, 2, 20, 0, tzinfo=timezone(timedelta(hours=8)))
    s.add_oneshot("开会", aware)
    s.arm(datetime(2026, 8, 2, 19, 0))
    ev = s.tick(datetime(2026, 8, 2, 20, 0))
    assert len(ev) == 1 and ev[0]["message"] == "开会"


def test_multiple_due_events_in_one_tick():
    s = ReminderScheduler()
    s.add_daily("喝水", 8, 0)
    s.add_oneshot("开会", datetime(2026, 8, 2, 8, 0))
    s.arm(datetime(2026, 8, 2, 7, 0))
    ev = s.tick(datetime(2026, 8, 2, 8, 0))
    kinds = sorted(e["kind"] for e in ev)
    assert kinds == ["daily", "oneshot"]
    assert s.list_reminders()[0] == []   # oneshot 已被移除


def test_load_dict_normalizes_tzaware_oneshot():
    s = ReminderScheduler()
    s.load_dict(
        {"work_min": 25, "break_min": 5, "rounds": 4},
        {"oneshot": [{"id": "a", "label": "会议", "when": "2026-08-02T20:00:00+08:00"}], "daily": []},
    )
    oneshot, _ = s.list_reminders()
    assert len(oneshot) == 1
    assert oneshot[0]["when"] == "2026-08-02T20:00:00"   # tzinfo 已剥离
    s.arm(datetime(2026, 8, 2, 19, 0))
    ev = s.tick(datetime(2026, 8, 2, 20, 0))
    assert len(ev) == 1 and ev[0]["message"] == "会议"    # 能正常触发


def test_corrupt_entry_in_memory_does_not_crash_tick():
    s = ReminderScheduler()
    s._oneshot = [{"id": "x", "label": "坏", "when": "不是日期"}]
    s._daily = [{"id": "y", "label": "坏", "hour": 99, "minute": 0}]
    s.arm(datetime(2026, 8, 2, 7, 0))
    assert s.tick(datetime(2026, 8, 2, 8, 0)) == []   # 不抛，也不触发


def test_oneshot_corrupt_entry_dropped_not_zombie():
    s = ReminderScheduler()
    s._oneshot = [{"id": "z", "label": "坏", "when": "不是日期", "fired": False}]
    s.tick(datetime(2026, 1, 1, 0, 0, 0))
    assert s._oneshot == [], "不可解析条目应被丢弃而非永久保留"


def test_oneshot_missing_key_dropped_not_keyerror():
    s = ReminderScheduler()
    s._oneshot = [
        {"id": "a", "label": "缺 when 键", "fired": False},
        {"id": "b", "when": "2026-01-01T00:00:00", "fired": False},
    ]
    assert s.tick(datetime(2026, 1, 1, 0, 0, 0)) == []
    assert s._oneshot == [], "缺键条目应被丢弃，且不抛 KeyError 中断整轮 tick"


def test_tick_before_arm_daily_still_works():
    s = ReminderScheduler()
    s.add_daily("早会", 9, 0)
    evs = s.tick(datetime(2026, 1, 1, 8, 0, 0))   # 未 arm，首次 tick 设基准
    assert evs == []
    evs = s.tick(datetime(2026, 1, 1, 9, 0, 30))
    assert any(e["kind"] == "daily" for e in evs), "未显式 arm 时每日提醒应仍可用"
