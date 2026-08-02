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
    except (TypeError, ValueError, OverflowError):
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
        when_dt = datetime.fromisoformat(when)
    except ValueError:
        return None
    if when_dt.tzinfo is not None:
        when_dt = when_dt.replace(tzinfo=None)
        when = when_dt.isoformat()
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
    except (TypeError, ValueError, OverflowError):
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

    def remove(self, rid):
        self._oneshot = [e for e in self._oneshot if e["id"] != rid]
        self._daily = [e for e in self._daily if e["id"] != rid]

    def list_reminders(self):
        return [dict(e) for e in self._oneshot], [dict(e) for e in self._daily]

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
    def arm(self, now=None):
        """启动时调用一次：设 _last_tick = now，使每日提醒不补发启动前已过时刻。"""
        self._last_tick = now or self._now_fn()

    def tick(self, now=None):
        """推进状态，返回到期事件列表。事件形如 {"kind","title","message"}。"""
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

    def _tick_oneshot(self, now):
        events = []
        remaining = []
        for e in self._oneshot:
            try:
                when = datetime.fromisoformat(e["when"])
                label = e["label"]
                due = now >= when
            except (ValueError, TypeError, KeyError):
                # 损坏条目（不可解析 / 缺键 / 带时区）直接丢弃，不再出现在 to_dict 输出，
                # 与 fired 条目的移除生命周期一致，非数据丢失
                continue
            if due:
                events.append({"kind": "oneshot", "title": "提醒", "message": label})
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
