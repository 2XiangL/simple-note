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
