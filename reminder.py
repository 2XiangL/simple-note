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
