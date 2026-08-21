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
