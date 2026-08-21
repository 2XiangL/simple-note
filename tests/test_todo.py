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
    c = s.add("C")
    s.set_current(a["id"])
    s.toggle(a["id"])          # A 完成 -> 沉到已完成组末尾 + 解除 current
    assert s.current_id() is None
    assert _texts(s) == ["B", "C", "A"]
    s.toggle(a["id"])          # 取消完成 -> 回未完成组末尾（B、C 之后）
    assert _texts(s) == ["B", "C", "A"]
    assert [e["done"] for e in s.list_items()] == [False, False, False]


def test_move_within_segment_only():
    s = todo.TodoStore()
    a = s.add("A")
    b = s.add("B")
    c = s.add("C")
    s.toggle(c["id"])          # [A, B, C*]
    s.move(c["id"], -1)        # 跨段上移 -> no-op
    assert _texts(s) == ["A", "B", "C"]
    s.move(b["id"], -1)        # 段内上移 -> [B, A, C*]
    assert _texts(s) == ["B", "A", "C"]
    s.move(b["id"], -1)        # 段首再上移 -> no-op
    assert _texts(s) == ["B", "A", "C"]
    s.move("不存在", 1)        # 未知 id -> no-op
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
