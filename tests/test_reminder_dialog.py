import reminder
from reminder_dialog import ReminderDialog, _valid_hhmm


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
